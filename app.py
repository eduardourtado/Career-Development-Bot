import streamlit as st
import os 
from google import genai
from google.genai.errors import APIError
from google.genai.types import Content, Part

# --- 1. Configuração da Interface ---
st.set_page_config(page_title="Mentor de Carreira PDI (Gemini)", page_icon="🎯", layout="centered")

st.title("🎯 Mentor de PDI Inteligente (Gemini)")
st.markdown("Olá! Sou seu assistente de carreira. Vamos construir seu **Plano de Desenvolvimento Individual** juntos.")

# --- CSS para Layout Preto/Branco (Mantido) ---
st.markdown("""
<style>
    .stApp {background-color: #000000; color: #FFFFFF;}
    h1, h2, h3, h4, p, .stMarkdown {color: #FFFFFF !important;}
    .block-container {padding-top: 2rem; padding-bottom: 0rem; padding-left: 2rem; padding-right: 2rem; max-width: 800px;}
    .stChatMessage {border-radius: 15px; padding: 15px; background-color: #1A1A1A; color: #FFFFFF !important; border: 1px solid #444444;}
    .stTextInput > div > div > input, .stTextInput > label {
        color: #FFFFFF; background-color: #000000; border: 1px solid #FFFFFF; border-radius: 8px;
    }
    .stButton>button {display: none;} /* Oculta todos os st.button simples */
    header {visibility: hidden; height: 0px;}
    footer {visibility: hidden; height: 0px;}
    #MainMenu {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# --- 2. Variáveis de Estado e Perguntas PERSONALIZADAS ---

# Lista de perguntas e introduções para serem feitas sequencialmente.
# O tipo 'input' usa st.chat_input, o tipo 'select' usa st.radio.
QUESTION_FLOW = [
    # Bloco 1: Configurações (st.radio)
    {"type": "intro", "text": "Antes de começarmos, vamos configurar o **idioma e o estilo de resposta** do nosso Mentor. Isso garante uma comunicação perfeita!"},
    {"type": "select", "question": "Em qual idioma você prefere que o Mentor de PDI responda? (Obrigatório para o System Prompt)", 
     "key": "lang", "options": ["Português", "Inglês", "Espanhol"]},
    {"type": "select", "question": "Qual tom/estilo de resposta você prefere do seu Mentor?", 
     "key": "style", "options": ["Profissional e Objetivo", "Empático e Encorajador", "Direto e Desafiador"]},

    # Bloco 2: Sobre Você (st.chat_input)
    {"type": "intro", "text": "Ótimo! Agora, começarei fazendo algumas perguntas sobre você. Tudo bem?"},
    {"type": "input", "question": "Como você preferiria que eu te chamasse?"},
    {"type": "input", "question": "Quantos anos você tem?"},

    # Bloco 3: Experiências Educacionais (st.chat_input)
    {"type": "intro", "text": "Perfeito. Agora, gostaria de explorarmos mais detalhes sobre suas **experiências educacionais**."},
    {"type": "input", "question": "Qual foi o maior nível de educação que você já obteve? (Ex: Bacharelado, Mestrado, Pós-doutorado)"},
    {"type": "input", "question": "Em qual instituição você obteve essa formação?"},
    {"type": "input", "question": "Qual foi a sua área de estudo?"},

    # Bloco 4: Experiência Profissional (st.chat_input)
    {"type": "intro", "text": "Entendido. Vamos agora para o bloco de **experiência profissional**."},
    {"type": "input", "question": "Você já trabalhou como jovem aprendiz? Se sim, em qual ano foi sua primeira experiência nesse formato?"},
    {"type": "input", "question": "Você já trabalhou como estagiário(a)? Se sim, em qual ano foi sua primeira experiência nesse formato?"},
    {"type": "input", "question": "Você já trabalhou como funcionário CLT? Se sim, em qual ano foi sua primeira experiência nesse formato?"},
    {"type": "input", "question": "Por favor, cite os nomes das empresas nas quais você já trabalhou como CLT (separe por vírgulas)"},
    {"type": "input", "question": "Você está trabalhando atualmente? Se sim, cite qual é o nome da sua posição e empresa atuais"},

    # Bloco 5: Objetivos Profissionais (st.chat_input)
    {"type": "intro", "text": "Para finalizar nosso formulário, vamos focar nos seus **objetivos profissionais**."},
    {"type": "input", "question": "Quais são os seus principais objetivos profissionais?"}
]
NUM_FLOW_STEPS = len(QUESTION_FLOW)

# --- 3. Carregamento Secreto da Chave ---
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# --- 4. Lógica de Memória (Histórico) ---
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "system", "content": ""}] # System prompt será montado
    st.session_state.pdi_state = 0 
    st.session_state.configs = {} # Armazena as respostas de select (idioma, estilo)


# Função para montar o System Prompt baseado nas configurações
def build_system_prompt():
    lang = st.session_state.configs.get('lang', 'Português')
    style = st.session_state.configs.get('style', 'Profissional e Objetivo')
    
    # Este prompt será injetado no índice 0 do histórico antes da chamada final ao Gemini
    return f"""
        Você é um Mentor de Carreira Sênior especializado em criar Planos de Desenvolvimento Individual (PDI).
        
        INSTRUÇÕES DE RESPOSTA:
        1. IDIOMA PRINCIPAL: Responda **APENAS em {lang}**, independente do idioma que o usuário usar nas entradas de texto.
        2. TOM DE VOZ: Use um tom de voz **{style}**.
        
        SUA MISSÃO:
        Você acaba de receber as respostas iniciais do usuário, que cobrem: Nome, Idade, Educação, Experiências Profissionais, Posição Atual e Objetivos.
        
        1. REVISE E VALIDE: Revise as respostas. Se alguma informação crucial parecer incompleta, peça esclarecimento de forma educada, mantendo o estilo de voz definido.
        2. INICIE A ANÁLISE: Após a validação, comece a etapa 2 do PDI: 'Identificar Gaps (O que falta aprender?)'. Baseie-se nas experiências passadas e nos objetivos futuros.
        """

# Função para gerar o conteúdo usando o Gemini (mantida a lógica estável)
def generate_gemini_response(prompt, api_key):
    # Garante que o system prompt é o primeiro item
    st.session_state.messages[0]['content'] = build_system_prompt()
    system_prompt = st.session_state.messages[0]['content']

    if not api_key: st.error("Erro de configuração: A chave GEMINI_API_KEY não foi encontrada.") ; return None
        
    try:
        client = genai.Client(api_key=api_key)
        history_messages = []
        for m in st.session_state.messages[1:]:
            role = 'user' if m['role'] == 'user' else 'model'
            content_obj = Content(role=role, parts=[Part.from_text(text=m['content'])]) 
            history_messages.append(content_obj)
        
        history_messages.append(Content(role='user', parts=[Part.from_text(text=prompt)]))

        response = client.models.generate_content(
            model='gemini-2.5-flash', contents=history_messages, config={'system_instruction': system_prompt} 
        )
        return response
    
    except APIError as e: st.error(f"Erro na API do Gemini: Detalhe: {e}"); return None
    except Exception as e: st.error(f"Ocorreu um erro inesperado: {e}"); return None


# Exibir mensagens anteriores no chat
for msg in st.session_state.messages:
    if msg["role"] != "system":
        role = 'assistant' if msg["role"] == 'model' else msg["role"]
        st.chat_message(role).write(msg["content"])


# --- 5. Lógica da Máquina de Estados (Controle do Fluxo) ---

# Checa se o fluxo de perguntas não terminou
if st.session_state.pdi_state < NUM_FLOW_STEPS:
    
    current_step = QUESTION_FLOW[st.session_state.pdi_state]
    
    # 5.1. Exibir Introdução
    if current_step["type"] == "intro":
        st.chat_message("assistant").write(current_step["text"])
        st.session_state.pdi_state += 1
        st.rerun()

    # 5.2. Exibir Múltipla Escolha (st.radio)
    elif current_step["type"] == "select":
        st.chat_message("assistant").write(current_step["question"])
        
        # Cria um contêiner para posicionar o radio button e o botão de avançar
        with st.container():
            selected_option = st.radio("Selecione uma opção:", current_step["options"], key=f'select_{st.session_state.pdi_state}')
            
            # Botão personalizado (usa markdown para aparecer, pois o st.button está escondido)
            # O texto do botão deve ser clicável.
            if st.markdown(f'<a href="#" target="_self"><button style="color:white; background-color:#4A90E2; border-radius:5px; padding:10px;">Confirmar e Continuar</button></a>', unsafe_allow_html=True):
                # Armazena a configuração
                st.session_state.configs[current_step["key"]] = selected_option
                
                # Registra a resposta no histórico como se fosse o usuário
                st.session_state.messages.append({"role": "user", "content": f"{current_step['question']}: {selected_option}"})
                
                st.session_state.pdi_state += 1 
                st.rerun()
        
        st.stop() # Interrompe o fluxo para que o chat_input não apareça

    # 5.3. Exibir Pergunta de Texto (st.chat_input)
    elif current_step["type"] == "input":
        st.chat_message("assistant").write(current_step["question"])
        # A lógica para capturar a resposta está abaixo, no st.chat_input


# 5.4. Captura a interação do usuário (apenas para type="input")
if prompt := st.chat_input("Digite sua resposta aqui..."):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    if st.session_state.pdi_state < NUM_FLOW_STEPS:
        # Aumenta o estado se a resposta foi uma entrada de texto
        st.session_state.pdi_state += 1
        
        if st.session_state.pdi_state < NUM_FLOW_STEPS:
            st.rerun() 
        else:
            # Transição final para o Chat Ativo
            with st.chat_message("assistant"):
                st.markdown("✅ **Formulário inicial completo!** O Mentor de Carreira já está analisando suas respostas. Por favor, aguarde enquanto ele processa a primeira análise e inicia a fase de identificação de *Gaps*.")
                
            # Chama o Gemini com a última resposta como prompt inicial
            final_prompt_to_gemini = st.session_state.messages[-1]['content']
            
            with st.chat_message("assistant"):
                response = generate_gemini_response(final_prompt_to_gemini, gemini_api_key)
                if response:
                    full_response = response.text
                    st.markdown(full_response)
                    st.session_state.messages.append({"role": "model", "content": full_response})
                else:
                    st.session_state.messages.pop()
    else:
        # 5.5. Chat Ativo (Gemini assume)
        with st.chat_message("assistant"):
            response = generate_gemini_response(prompt, gemini_api_key)
            
            if response:
                full_response = response.text
                st.markdown(full_response)
                st.session_state.messages.append({"role": "model", "content": full_response})
            else:
                st.session_state.messages.pop()

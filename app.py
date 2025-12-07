import streamlit as st
import os 
from google import genai
from google.genai.errors import APIError
from google.genai.types import Content, Part

# --- 1. Configuração da Interface ---
st.set_page_config(page_title="Mentor de Carreira PDI (Gemini)", page_icon="🎯", layout="centered")

st.title("🎯 Mentor de PDI Inteligente (Gemini)")
st.markdown("Olá! Sou seu assistente de carreira. Vamos construir seu **Plano de Desenvolvimento Individual** juntos.")

# --- CSS para Layout Preto/Branco e Estabilidade ---
st.markdown("""
<style>
    /* 1. Estilos de Cores */
    .stApp {background-color: #000000; color: #FFFFFF;}
    h1, h2, h3, h4, p, .stMarkdown {color: #FFFFFF !important;}
    
    /* 2. Largura e Padding */
    .block-container {padding-top: 2rem; padding-bottom: 0rem; padding-left: 2rem; padding-right: 2rem; max-width: 800px;}
    
    /* 3. Estilo das Caixas de Mensagem */
    .stChatMessage {border-radius: 15px; padding: 15px; background-color: #1A1A1A; color: #FFFFFF !important; border: 1px solid #444444;}
    
    /* 4. Estilo da Barra de Input de Mensagem */
    .stTextInput > div > div > input, .stTextInput > label {
        color: #FFFFFF; background-color: #000000; border: 1px solid #FFFFFF; border-radius: 8px;
    }
    
    /* 5. CORREÇÃO DE LEGIBILIDADE PARA ST.RADIO E ST.SELECT */
    .stRadio > label, .stRadio > div > label > div > div > p {
        color: #FFFFFF !important; 
    }
    
    /* 6. Oculta st.button simples (só aparecem os de formulário) */
    .stButton>button {display: none;}
    
    /* 7. OCULTA BARRAS DE CABEÇALHO E RODAPÉ */
    header {visibility: hidden; height: 0px;}
    footer {visibility: hidden; height: 0px;}
    #MainMenu {visibility: hidden;}
    
    /* 8. Estilo do botão de formulário para que ele apareça */
    div.stButton > button {
        display: inline-block; 
        color: white; 
        background-color: #4A90E2; 
        border: none;
        border-radius: 5px; 
        padding: 10px 15px;
        cursor: pointer;
    }
</style>
""", unsafe_allow_html=True)


# --- 2. Variáveis de Estado e Perguntas PERSONALIZADAS ---
QUESTION_FLOW = [
    # Bloco 1: Configurações (st.radio)
    {"type": "intro", "text": "Antes de começarmos, vamos configurar o **idioma e o estilo de resposta** do nosso Mentor. Isso garante uma comunicação perfeita!"},
    {"type": "select", "question": "Em qual idioma você prefere que o Mentor de PDI responda?", 
     "key": "lang", "options": ["Português", "Inglês", "Espanhol"]},
    {"type": "select", "question": "Qual estilo de interação você prefere?", 
     "key": "style", "options": ["Extrovertido", "Profissional"]},
    {"type": "select", "question": "Você prefere respostas com mais ou menos detalhes?", 
     "key": "detail", "options": ["Muito Detalhe", "Direto ao Ponto"]},

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

# --- 4. Lógica de Memória (Histórico e Estado) ---
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "system", "content": ""}] 
    st.session_state.pdi_state = 0 
    st.session_state.configs = {} 

# Função que executa o submit do formulário de seleção
def submit_form(key, question):
    selected_option = st.session_state[f'select_{st.session_state.pdi_state}']

    # 1. Armazena a configuração
    st.session_state.configs[key] = selected_option
    
    # 2. Registra a resposta do usuário no histórico
    st.session_state.messages.append({"role": "user", "content": f"{question}: {selected_option}"})
    
    # 3. Avança o estado e força a reexecução
    st.session_state.pdi_state += 1 
    st.rerun() 


# Função para montar o System Prompt baseado nas configurações
def build_system_prompt():
    lang = st.session_state.configs.get('lang', 'Português')
    style = st.session_state.configs.get('style', 'Profissional')
    detail = st.session_state.configs.get('detail', 'Muito Detalhe')
    
    return f"""
        Você é um Mentor de Carreira Sênior especializado em criar Planos de Desenvolvimento Individual (PDI).
        
        INSTRUÇÕES DE COMPORTAMENTO RÍGIDAS:
        1. EDUCAÇÃO: Você **DEVE** ser sempre cortês, educado e profissional. **NUNCA** use linguagem passivo-agressiva ou grosseira, mesmo ao pedir esclarecimentos ou ao criticar objetivos.
        2. IDIOMA PRINCIPAL: Responda APENAS em {lang}.
        3. TOM E DETALHE: O tom de voz deve ser {style} e o nível de profundidade deve ser {detail}. Se for 'Direto ao Ponto', use listas e parágrafos curtos.
        
        SUA MISSÃO:
        Você acaba de receber as respostas iniciais do usuário.
        
        1. REVISE E VALIDE: Revise as respostas com o tom {style}. Se alguma informação crucial parecer incompleta, peça esclarecimento de forma **educada**.
        2. INICIE A ANÁLISE: Após a validação, comece a etapa 2 do PDI: 'Identificar Gaps (O que falta aprender?)'. Baseie-se nas experiências e objetivos.
        """

# Função para gerar o conteúdo usando o Gemini
def generate_gemini_response(prompt, api_key):
    st.session_state.messages[0]['content'] = build_system_prompt()
    system_prompt = st.session_state.messages[0]['content']

    if not api_key: st.error("Erro de configuração: A chave GEMINI_API_KEY não foi encontrada."); return None
        
    try:
        client = genai.Client(api_key=api_key)
        
        history_messages = []
        for m in st.session_state.messages[1:]:
            role = 'user' if m['role'] == 'user' else 'model'
            content_obj = Content(role=role, parts=[Part.from_text(text=m['content'])]) 
            history_messages.append(content_obj)
        
        history_messages.append(Content(role='user', parts=[Part.from_text(text=prompt)]))

        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=history_messages, 
            config={'system_instruction': system_prompt} 
        )
        return response
    
    except APIError as e: st.error(f"Erro na API do Gemini: Detalhe: {e}"); return None
    except Exception as e: st.error(f"Ocorreu um erro inesperado: {e}"); return None


# --- 5. Lógica da Máquina de Estados (Controle do Fluxo) ---

# Exibir mensagens anteriores no chat
for msg in st.session_state.messages:
    # Ignoramos a mensagem do "system" (índice 0)
    if msg["role"] != "system":
        role = 'assistant' if msg["role"] == 'model' else msg["role"]
        # Se a mensagem foi salva, ela será exibida aqui
        st.chat_message(role).write(msg["content"])


# Lógica para avançar o formulário ou iniciar o chat
if st.session_state.pdi_state < NUM_FLOW_STEPS:
    
    current_step = QUESTION_FLOW[st.session_state.pdi_state]
    
    # 5.1. Exibir Introdução E SALVAR NO HISTÓRICO
    if current_step["type"] == "intro":
        # A mensagem é exibida para o usuário (como assistente)
        st.chat_message("assistant").write(current_step["text"])
        
        # A MENSAGEM É SALVA NO HISTÓRICO PARA EXIBIÇÃO FUTURA
        st.session_state.messages.append({"role": "model", "content": current_step["text"]})
        
        st.session_state.pdi_state += 1
        st.rerun()

    # 5.2. Exibir Múltipla Escolha (st.radio) E SALVAR PERGUNTA NO HISTÓRICO
    elif current_step["type"] == "select":
        # A pergunta é exibida para o usuário (como assistente)
        st.chat_message("assistant").write(current_step["question"])
        
        # A PERGUNTA É SALVA NO HISTÓRICO
        # (A resposta será salva dentro da submit_form)
        st.session_state.messages.append({"role": "model", "content": current_step["question"]})

        with st.form(key=f'form_{st.session_state.pdi_state}'):
            st.radio("Selecione uma opção:", 
                     current_step["options"], 
                     key=f'select_{st.session_state.pdi_state}')
            
            st.form_submit_button(
                "Confirmar e Continuar", 
                on_click=submit_form, 
                kwargs={'key': current_step["key"], 'question': current_step["question"]}
            )
        
        st.stop() 

    # 5.3. Exibir Pergunta de Texto (st.chat_input) E SALVAR NO HISTÓRICO
    elif current_step["type"] == "input":
        # A pergunta é exibida para o usuário (como assistente)
        st.chat_message("assistant").write(current_step["question"])
        
        # A PERGUNTA É SALVA NO HISTÓRICO
        st.session_state.messages.append({"role": "model", "content": current_step["question"]})
        # A lógica para capturar a resposta está abaixo, no st.chat_input


# 5.4. Captura a interação do usuário (apenas para type="input")
if prompt := st.chat_input("Digite sua resposta aqui..."):
    
    # A resposta do usuário já é salva aqui
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

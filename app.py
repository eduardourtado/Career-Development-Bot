import streamlit as st
import os # Necessário para buscar a chave secreta
from google import genai
from google.genai.errors import APIError
from google.genai.types import Content, Part

# --- 1. Configuração da Interface ---
st.set_page_config(page_title="Mentor de Carreira PDI (Gemini)", page_icon="🎯", layout="centered")

st.title("Mentor de PDI Inteligente (Gemini)")
st.markdown("Olá! Sou seu assistente de carreira. Vamos construir seu **Plano de Desenvolvimento Individual** juntos. Por favor, responda o formulário inicial para um planejamento eficaz.")

st.markdown("""
<style>
    .stChatMessage {
        border-radius: 10px; 
        padding: 10px;
    }
</style>
""", unsafe_allow_html=True)


# --- 2. Variáveis de Estado e Perguntas PERSONALIZADAS ---

# 11 Perguntas estruturadas em ordem
FORM_QUESTIONS = [
    # 1. Sobre você
    "1/11. Como você preferiria que eu te chamasse?",
    "2/11. Quantos anos você tem?",
    
    # 2. Sobre experiências educacionais
    "3/11. Qual foi o maior nível de educação que você já obteve? (Opções: Ensino Fundamental, Ensino Médio, Bacharelado / Licenciatura / Tecnólogo, Pós-graduação, M.B.A., Mestrado, Doutorado, Pós-doutorado, Nenhum a declarar)",
    "4/11. Em qual instituição você obteve essa formação?",
    "5/11. Qual foi a sua área de estudo?",
    
    # 3. Sobre experiência profissional
    "6/11. Você já trabalhou como jovem aprendiz? Se sim, em qual ano foi sua primeira experiência nesse formato?",
    "7/11. Você já trabalhou como estagiário(a)? Se sim, em qual ano foi sua primeira experiência nesse formato?",
    "8/11. Você já trabalhou como funcionário CLT? Se sim, em qual ano foi sua primeira experiência nesse formato?",
    "9/11. Por favor, cite os nomes das empresas nas quais você já trabalhou como CLT (separe por vírgulas)",
    "10/11. Você está trabalhando atualmente? Se sim, cite qual é o nome da sua posição e empresa atuais",
    
    # 4. Objetivos profissionais
    "11/11. Quais são os seus principais objetivos profissionais?"
]
NUM_QUESTIONS = len(FORM_QUESTIONS) # Total de 11 perguntas

# --- 3. Barra Lateral para Configuração ---
with st.sidebar:
    st.header("Configurações")
    st.write("A chave da API está sendo carregada de forma segura pelo servidor (Secrets).")
    
    # O INPUT DA CHAVE FOI REMOVIDO PARA OCULTAR DO USUÁRIO FINAL
    
    if st.button("Limpar Conversa"):
        st.session_state.messages = []
        st.session_state.pdi_state = 0
        st.rerun()

# --- CARREGAMENTO SECRETO DA CHAVE ---
# A chave é buscada da variável de ambiente definida no Streamlit Cloud (GEMINI_API_KEY)
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# --- 4. Lógica de Memória (Histórico) ---
if "messages" not in st.session_state:
    st.session_state["messages"] = [{
        "role": "system", 
        "content": """
        Você é um Mentor de Carreira Sênior especializado em criar Planos de Desenvolvimento Individual (PDI).
        
        SUA MISSÃO:
        Você acaba de receber as respostas iniciais do usuário, que cobrem: Nome, Idade, Educação, Experiências Profissionais (Aprendiz, Estágio, CLT), Empresas, Posição Atual e Objetivos.
        
        1. REVISE E VALIDE: Revise as 11 respostas do usuário. Se alguma informação parecer incompleta, peça esclarecimento de forma educada.
        2. INICIE A ANÁLISE: Após a validação, comece a etapa 2 do PDI: 'Identificar Gaps (O que falta aprender?)'. Baseie-se nas experiências passadas e nos objetivos futuros.
        
        TONALIDADE: Profissional, acolhedor e focado em resultado.
        """
    }]
    # Inicializa o estado do formulário
    st.session_state.pdi_state = 0 


# Função para gerar o conteúdo usando o Gemini
def generate_gemini_response(prompt, api_key):
    if not api_key:
        st.error("Erro de configuração: A chave GEMINI_API_KEY não foi encontrada no ambiente de hospedagem.")
        return None
        
    try:
        client = genai.Client(api_key=api_key)
        
        system_prompt = st.session_state.messages[0]['content']
        
        # Prepara o histórico
        history_messages = []
        for m in st.session_state.messages[1:]:
            role = 'user' if m['role'] == 'user' else 'model'
            content_obj = Content(
                role=role,
                parts=[Part.from_text(text=m['content'])] 
            )
            history_messages.append(content_obj)
        
        # Adiciona a nova mensagem do usuário no formato Content
        history_messages.append(Content(role='user', parts=[Part.from_text(text=prompt)]))

        # A chamada à API
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=history_messages,
            config={'system_instruction': system_prompt} 
        )
        
        return response
    
    except APIError as e:
        st.error(f"Erro na API do Gemini: Verifique se sua chave secreta é válida e tem créditos. Detalhe: {e}")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado: {e}")
        return None


# Exibir mensagens anteriores no chat
for msg in st.session_state.messages:
    if msg["role"] != "system":
        role = 'assistant' if msg["role"] == 'model' else msg["role"]
        st.chat_message(role).write(msg["content"])


# --- 5. Lógica da Máquina de Estados (Controle das 11 Perguntas) ---

# 5.1. Exibir a próxima pergunta do formulário
if st.session_state.pdi_state < NUM_QUESTIONS:
    next_question = FORM_QUESTIONS[st.session_state.pdi_state]
    # O bot sempre fala a próxima pergunta no início
    st.chat_message("assistant").write(next_question)


# 5.2. Captura a interação do usuário
if prompt := st.chat_input("Digite sua resposta aqui..."):
    
    # Adiciona a mensagem do usuário ao histórico e exibe
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # Lógica de Transição de Estado:
    if st.session_state.pdi_state < NUM_QUESTIONS:
        # Estamos no meio do formulário. Aumenta o estado para a próxima pergunta.
        st.session_state.pdi_state += 1
        
        if st.session_state.pdi_state < NUM_QUESTIONS:
            # Recarrega para mostrar a próxima pergunta
            st.rerun() 
        else:
            # Transição para o chat ativo (Formulário completo)
            
            # Exibir uma mensagem de transição
            with st.chat_message("assistant"):
                st.markdown("✅ **Formulário inicial completo!** O Mentor de Carreira já está analisando suas 11 respostas. Por favor, aguarde enquanto ele processa a primeira análise e inicia a fase de identificação de *Gaps*.")
                
            # Na próxima execução, o fluxo cairá no bloco ELSE (Chat Ativo)
            # Para forçar a primeira resposta do Gemini sem nova interação do usuário:
            # Vamos reutilizar a última resposta do usuário como o prompt de ativação.
            final_prompt_to_gemini = st.session_state.messages[-1]['content']
            
            # Chama o Gemini com a última resposta como prompt inicial
            with st.chat_message("assistant"):
                response = generate_gemini_response(final_prompt_to_gemini, gemini_api_key)
                if response:
                    full_response = response.text
                    st.markdown(full_response)
                    st.session_state.messages.append({"role": "model", "content": full_response})
                else:
                    st.session_state.messages.pop()
    else:
        # 5.3. Chat Ativo (Gemini)
        
        # Inicia a geração
        with st.chat_message("assistant"):
            response = generate_gemini_response(prompt, gemini_api_key)
            
            if response:
                full_response = response.text
                st.markdown(full_response)
                
                # Salva a resposta do bot na memória
                st.session_state.messages.append({"role": "model", "content": full_response})
            else:
                st.session_state.messages.pop()

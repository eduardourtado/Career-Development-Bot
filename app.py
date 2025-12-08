import streamlit as st
import os 
from google import genai
from google.genai.errors import APIError
from google.genai.types import Content, Part
from fpdf.fpdf import FPDF 
from datetime import datetime

# --- Função de Limpeza de Estado ---
def clear_session_state():
    """Reinicia todas as variáveis de estado da sessão."""
    st.session_state["messages"] = [{"role": "system", "content": ""}] 
    st.session_state.pdi_state = 0 
    st.session_state.configs = {} 
    st.session_state.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if 'generate_summary' in st.session_state:
        del st.session_state['generate_summary']


# --- 1. Configuração da Interface ---
st.set_page_config(page_title="Mentor de Carreira PDI (Gemini)", page_icon="🎯", layout="centered")

st.title("🎯 Mentor de PDI Inteligente (Gemini)")
st.markdown("Olá! Sou seu assistente de carreira. Vamos construir seu **Plano de Desenvolvimento Individual** juntos. Por favor, responda o formulário inicial para um planejamento eficaz.")

# --- CSS para Layout Preto/Branco e Estabilidade ---
st.markdown("""
<style>
    /* ... CSS OMITIDO POR CONCISÃO ... */
    .stApp {background-color: #000000; color: #FFFFFF;}
    h1, h2, h3, h4, p, .stMarkdown {color: #FFFFFF !important;}
    .block-container {padding-top: 2rem; padding-bottom: 0rem; padding-left: 2rem; padding-right: 2rem; max-width: 800px;}
    .stChatMessage {border-radius: 15px; padding: 15px; background-color: #1A1A1A; color: #FFFFFF !important; border: 1px solid #444444;}
    .stRadio > label, .stRadio > div > label > div > div > p {color: #FFFFFF !important;}
    div.stButton > button {background-color: #4A90E2; color: #FFFFFF; border: none; border-radius: 5px; padding: 10px 15px; cursor: pointer;}
    div[data-testid="stForm"] div.stButton button {
        color: #FFFFFF !important; 
        background-color: #000000 !important; 
        border: 2px solid #FFFFFF !important; 
        box-shadow: 0 0 5px rgba(255, 255, 255, 0.5);
    }
    div[data-testid="stForm"] div.stButton button span {color: #FFFFFF !important;}
    header {visibility: hidden; height: 0px;}
    footer {visibility: hidden; height: 0px;}
    #MainMenu {visibility: hidden;}
    
</style>
""", unsafe_allow_html=True)


# --- 2. Variáveis de Estado e Perguntas PERSONALIZADAS ---
QUESTION_FLOW = [
    {"type": "intro", "text": "Antes de começarmos, vamos configurar o **idioma e o estilo de resposta** do nosso Mentor. Isso garante uma comunicação perfeita!"},
    {"type": "select", "question": "Em qual idioma você prefere que o Mentor de PDI responda?", 
     "key": "lang", "options": ["Português", "Inglês", "Espanhol"]},
    {"type": "select", "question": "Qual estilo de interação você prefere?", 
     "key": "style", "options": ["Extrovertido", "Profissional"]},
    {"type": "select", "question": "Você prefere respostas com mais ou menos detalhes?", 
     "key": "detail", "options": ["Muito Detalhe", "Direto ao Ponto"]},
    {"type": "intro", "text": "Ótimo! Agora, começarei fazendo algumas perguntas sobre você. Tudo bem?"},
    {"type": "input", "question": "Como você preferiria que eu te chamasse?"},
    {"type": "input", "question": "Quantos anos você tem?"},
    {"type": "intro", "text": "Perfeito. Agora, gostaria de explorarmos mais detalhes sobre suas **experiências educacionais**."},
    {"type": "input", "question": "Qual foi o maior nível de educação que você já obteve? (Ex: Bacharelado, Mestrado, Pós-doutorado)"},
    {"type": "input", "question": "Em qual instituição você obteve essa formação?"},
    {"type": "input", "question": "Qual foi a sua área de estudo?"},
    {"type": "intro", "text": "Entendido. Vamos agora para o bloco de **experiência profissional**."},
    {"type": "input", "question": "Você já trabalhou como jovem aprendiz? Se sim, em qual ano foi sua primeira experiência nesse formato?"},
    {"type": "input", "question": "Você já trabalhou como estagiário(a)? Se sim, em qual ano foi sua primeira experiência nesse formato?"},
    {"type": "input", "question": "Você já trabalhou como funcionário CLT? Se sim, em qual ano foi sua primeira experiência nesse formato?"},
    {"type": "input", "question": "Por favor, cite os nomes das empresas nas quais você já trabalhou como CLT (separe por vírgulas)"},
    {"type": "input", "question": "Você está trabalhando atualmente? Se sim, cite qual é o nome da sua posição e empresa atuais"},
    {"type": "intro", "text": "Para finalizar nosso formulário, vamos focar nos seus **objetivos profissionais**."},
    {"type": "input", "question": "Quais são os seus principais objetivos profissionais?"}
]
NUM_FLOW_STEPS = len(QUESTION_FLOW)

# --- 3. Carregamento Secreto da Chave ---
gemini_api_key = os.environ.get("GEMINI_API_KEY")

# --- 4. Lógica de Memória (Histórico e Estado) ---
if "messages" not in st.session_state:
    clear_session_state() 

# --- FUNÇÕES DE GERAÇÃO E DOWNLOAD ---

def get_user_name():
    """Busca o nome preferido do usuário no histórico da conversa."""
    name_question = "Como você preferiria que eu te chamasse?"
    for msg in st.session_state.messages:
        if msg["role"] == "user" and name_question in msg["content"]:
            try:
                name = msg["content"].split(':')[-1].strip()
                if name:
                    return name
            except:
                pass
    return "Usuário(a)" 

def format_transcript_data(messages):
    """Formata o histórico de mensagens em uma lista de tuplas (role, content)."""
    data = []
    user_name = get_user_name()
    for msg in messages[1:]:
        role = "Mentor" if msg["role"] == "model" else user_name
        data.append((role, msg["content"]))
    return data

def clean_and_encode_text(text):
    """
    Limpa o texto de Markdown e garante que qualquer caractere complexo seja substituído.
    (Usando UTF-8 para melhor compatibilidade com caracteres Unicode complexos)
    """
    clean = text.replace("`", "'").replace("**", "").replace("*", "")
    return clean.encode('utf-8', 'replace').decode('utf-8')

def pdf_print_content(pdf, data):
    """
    Imprime o conteúdo formatado no PDF com cores, negrito e um layout mais limpo.
    (Melhoria Estética)
    """
    
    MENTOR_BLUE = (100, 180, 255)   # Azul mais claro para maior contraste
    USER_GREEN = (150, 255, 150)     # Verde mais claro
    WHITE = (255, 255, 255)      
    
    INDENT_WIDTH = 5.0 # Largura do recuo do texto
    LINE_HEIGHT = 6.0 # Altura da linha um pouco maior para espaçamento
    
    for role, content in data:
        clean_content = clean_and_encode_text(content)

        # 1. Impressão do Cabeçalho do Turno
        if role == "Mentor":
            pdf.set_text_color(*MENTOR_BLUE)
            pdf.set_font("Helvetica", style="B", size=11)
        else:
            pdf.set_text_color(*USER_GREEN)
            pdf.set_font("Helvetica", style="B", size=11)
        
        # Adiciona uma margem superior para separar os turnos
        pdf.ln(3) 

        # Imprime o título do turno (sem recuo)
        pdf.cell(0, LINE_HEIGHT, f"🗣️ {role}:", ln=1) 

        # 2. Impressão do Conteúdo (Texto Limpo)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", size=10)
        
        # Inicia com uma célula vazia para recuo
        pdf.cell(INDENT_WIDTH, 0, "", 0, 0)
        
        # Imprime o conteúdo em multi_cell, ajustando a largura para o recuo
        text_width = pdf.w - pdf.l_margin - pdf.r_margin - INDENT_WIDTH
        
        # Usa o UTF-8 no multi_cell para garantir o máximo de caracteres
        pdf.multi_cell(
            text_width, 
            LINE_HEIGHT - 1.5, # Linha menor para texto corrido
            clean_content.encode('utf-8', 'replace').decode('utf-8'),
            align='L'
        )
        
        pdf.ln(3) # Espaço adicional após o conteúdo para separação


@st.cache_data(show_spinner="Gerando Resumo da Conversa com o Gemini...")
def generate_summary(history_messages, api_key):
    """Gera um resumo da conversa usando o Gemini."""
    if not api_key: return "Erro: Chave GEMINI_API_KEY não configurada."
    try:
        client = genai.Client(api_key=api_key)
        history_contents = []
        for m in history_messages[1:]:
            role = 'user' if m['role'] == 'user' else 'model'
            content_obj = Content(role=role, parts=[Part.from_text(text=m['content'])]) 
            history_contents.append(content_obj)
        summary_prompt = "Você é um Analista de Dados. Dada a conversa a seguir entre um Mentor de PDI e um Usuário, gere um resumo profissional e conciso dos pontos principais, focando nas respostas do usuário (experiências e objetivos) e na análise/dúvidas do Mentor. USE APENAS TEXTO, SEM MARKDOWN OU SÍMBOLOS."
        history_contents.append(Content(role='user', parts=[Part.from_text(text=summary_prompt)]))
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=history_contents
        )
        return response.text
    except APIError as e: 
        return f"Erro na API do Gemini ao gerar resumo: {e}"
    except Exception as e: 
        return f"Ocorreu um erro inesperado ao gerar resumo: {e}"

# --- FUNÇÃO PRINCIPAL DE GERAÇÃO DE PDF ---
def generate_pdf_bytes(content_data, title_suffix, is_summary=False):
    """Gera o PDF com layout escuro, personalizado e estruturado."""
    
    # Inicializa FPDF sem o argumento 'encoding' para evitar TypeError.
    pdf = FPDF(unit='mm', format='A4', orientation='P')
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    # --- 1. Fundo Preto (HACK) ---
    pdf.set_fill_color(0, 0, 0) # Preto RGB
    pdf.rect(0, 0, pdf.w, pdf.h, 'F') # Desenha um retângulo preto em toda a página

    # --- 2. Cabeçalho Personalizado (Branco) ---
    pdf.set_text_color(255, 255, 255) # Branco
    pdf.set_font("Helvetica", style="B", size=18)
    pdf.cell(0, 10, "🎯 Mentor de PDI Inteligente (Gemini)", ln=1, align="C")
    
    pdf.set_font("Helvetica", style="I", size=12)
    pdf.cell(0, 7, title_suffix, ln=1, align="C")
    
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 5, f"Data: {st.session_state.start_time}", ln=1, align="C")
    pdf.ln(8)
    
    # --- 3. Conteúdo ---
    
    if is_summary:
        # Modo Resumo (espera string)
        pdf.set_text_color(255, 255, 255) 
        pdf.set_font("Helvetica", size=11)
        
        clean_summary = clean_and_encode_text(content_data)
        
        # Usa UTF-8 na conversão do Resumo
        pdf.multi_cell(0, 6, clean_summary.encode('utf-8', 'replace').decode('utf-8'))
    else:
        # Modo Transcrição (espera lista de tuplas)
        pdf_print_content(pdf, content_data)
        
    # --- 4. Saída Final (Garantia de Bytes Seguros) ---
    # Força a saída para bytes compatíveis com Streamlit/PDF, contornando o erro interno do FPDF.
    return pdf.output(dest='S').encode('latin-1', 'replace')


# Função que executa o submit do formulário de seleção
def submit_form(key, question):
    selected_option = st.session_state[f'select_{st.session_state.pdi_state}']
    st.session_state.configs[key] = selected_option
    st.session_state.messages.append({"role": "user", "content": f"{question}: {selected_option}"})
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
        3. TOM E DETALHE: O tom de voz deve ser {style}. Se for 'Direto ao Ponto', use listas e parágrafos curtos, mantendo a polidez.
        
        SUA MISSÃO:
        Você acaba de receber as respostas iniciais do usuário. Revise, valide e inicie a fase de identificação de Gaps.
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
    if msg["role"] != "system":
        role = 'assistant' if msg["role"] == 'model' else msg["role"]
        st.chat_message(role).write(msg["content"])


# Lógica para avançar o formulário ou iniciar o chat
if st.session_state.pdi_state < NUM_FLOW_STEPS:
    
    current_step = QUESTION_FLOW[st.session_state.pdi_state]
    
    # 5.1. Exibir Introdução E SALVAR NO HISTÓRICO
    if current_step["type"] == "intro":
        intro_text = current_step["text"]
        st.chat_message("assistant").write(intro_text)
        
        if not st.session_state.messages or st.session_state.messages[-1]["content"] != intro_text:
            st.session_state.messages.append({"role": "model", "content": intro_text})
        
        st.session_state.pdi_state += 1
        st.rerun()

    # 5.2. Exibir Múltipla Escolha (st.radio)
    elif current_step["type"] == "select":
        question_text = current_step["question"]
        st.chat_message("assistant").write(question_text)
        
        if not st.session_state.messages or st.session_state.messages[-1]["content"] != question_text:
            st.session_state.messages.append({"role": "model", "content": question_text})

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

    # 5.3. Exibir Pergunta de Texto (st.chat_input)
    elif current_step["type"] == "input":
        question_text = current_step["question"]
        st.chat_message("assistant").write(question_text)

        if not st.session_state.messages or st.session_state.messages[-1]["content"] != question_text:
            st.session_state.messages.append({"role": "model", "content": question_text})


# 5.4. Captura a interação do usuário e Finaliza
if prompt := st.chat_input("Digite sua resposta aqui..."):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    if st.session_state.pdi_state < NUM_FLOW_STEPS:
        
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

# --- 6. BOTÕES DE AÇÃO E DOWNLOAD (Sempre Visíveis na Sidebar) ---

st.sidebar.subheader("⚙️ Ações")
st.sidebar.button("Limpar Conversa e Recomeçar", on_click=clear_session_state) 
st.sidebar.markdown("---")


# Geração de PDF (visível o tempo todo)
st.sidebar.subheader("🗂️ Download do Histórico")

# Transcrição Completa
transcript_data = format_transcript_data(st.session_state.messages)
pdf_full = generate_pdf_bytes(transcript_data, "Transcrição Completa", is_summary=False) 

st.sidebar.download_button(
    label="1️⃣ Transcrição Completa (PDF)",
    data=pdf_full,
    file_name=f"PDI_Transcricao_{datetime.now().strftime('%Y%m%d')}.pdf",
    mime="application/pdf"
)

# Resumo
if st.sidebar.button("2️⃣ Gerar Resumo (PDF)"):
    
    if st.session_state.pdi_state < NUM_FLOW_STEPS:
        st.warning("Aguarde a conclusão do formulário inicial para gerar um resumo significativo.")
    elif gemini_api_key:
        # Gera o resumo usando a função cacheada
        summary_text = generate_summary(st.session_state.messages, gemini_api_key)
        
        if summary_text.startswith(("Erro:", "Ocorreu um erro")):
             st.error(summary_text)
        else:
            # O Resumo é uma string simples, o PDF precisa saber que é um resumo
            pdf_summary = generate_pdf_bytes(summary_text, "Resumo da Análise (Gemini)", is_summary=True)
            
            # Reexibe o botão com os dados do PDF
            st.sidebar.download_button(
                label="✅ Baixar Resumo Gerado",
                data=pdf_summary,
                file_name=f"PDI_Resumo_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf"
            )
            st.success("Resumo gerado com sucesso! Clique para baixar.")
    else:
        st.error("Erro: A chave GEMINI_API_KEY não está configurada.")

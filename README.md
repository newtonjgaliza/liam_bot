# 🩺 Liam - Assistente Médico Pessoal no Telegram

O **Liam** é um assistente inteligente no Telegram construído para ajudar você e sua esposa com a rotina de saúde: agendamento de consultas com lembretes automáticos, leitura de receitas/exames/dietas em PDF ou foto com extração de remédios e dosagens, e respostas em linguagem natural sobre o histórico médico da família.

---

## 🌟 Principais Recursos

- **Lembretes Inteligentes de Consultas:**
  - Basta dizer: *"Liam, tenho consulta dia 12 de dezembro às 14h com Dra. Flávia"*
  - O Liam anota e dispara alertas automáticos:
    - 🔔 Na véspera da consulta (às 09:00)
    - ☀️ No próprio dia pela manhã (às 08:00)
    - ⏰ 2 horas antes do horário marcado
- **Leitura Multimodal de Documentos (PDFs e Fotos):**
  - Envie a receita, pedido de exame ou plano alimentar em PDF ou foto.
  - O Liam extrai automaticamente: médico, data, medicamentos, dosagem, frequência e orientações.
- **Memória & Respostas sobre o Histórico:**
  - *"Liam, quais remédios a Dra. Flávia passou na última consulta?"*
  - *"Qual foi a recomendação da nutricionista para o almoço?"*
  - *"Quando é a minha próxima consulta?"*
- **Comandos Rápidos:**
  - `/consultas`: Lista as próximas consultas agendadas.
  - `/remedios`: Exibe os medicamentos salvos no histórico.
  - `/ajuda`: Informações e exemplos de uso.

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.12
- **Telegram Bot:** `python-telegram-bot` v21 com `JobQueue` (APScheduler)
- **IA Multimodal:** Google Gemini (`gemini-2.5-flash` via `google-genai`)
- **Banco de Dados:** SQLite assíncrono via `SQLAlchemy` + `aiosqlite`
- **Containerização:** Docker e Docker Compose

---

## 🚀 Como Rodar Localmente com Docker

### 1. Configurar as variáveis de ambiente
Edite o arquivo `.env` gerado na raiz:

```env
TELEGRAM_BOT_TOKEN=9224474540:AAFpGj8sBzPUTShYXMOSnu9Bg03TzFR2UUs
GEMINI_API_KEY=sua_chave_do_google_ai_studio
ALLOWED_TELEGRAM_IDS=seu_id_do_telegram,id_da_sua_esposa
TIMEZONE=America/Sao_Paulo
PORT=8080
```

> **Dica:** Para pegar seu ID do Telegram, envie uma mensagem para o bot [@userinfobot](https://t.me/userinfobot). Se deixar `ALLOWED_TELEGRAM_IDS` em branco, qualquer pessoa que mandar `/start` poderá falar com ele.

### 2. Iniciar o container
```bash
docker compose up --build -d
```

Para ver os logs do Liam em tempo real:
```bash
docker compose logs -f
```

Para parar o bot:
```bash
docker compose down
```

---

## ☁️ Como Hospedar na Render (Passo a Passo)

A Render aceita repositórios Docker diretamente:

1. **Suba este projeto para um repositório no GitHub:**
   ```bash
   git init
   git add .
   git commit -m "feat: initial commit Liam bot"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/liam.git
   git push -u origin main
   ```
   *(O arquivo `.env` e as pastas `data/` e `uploads/` já estão protegidos pelo `.gitignore` e não serão enviados para o GitHub)*.

2. **Crie o serviço na Render:**
   - Acesse [dashboard.render.com](https://dashboard.render.com/) e clique em **New +** -> **Web Service**.
   - Conecte o repositório do GitHub que acabou de criar.
   - **Environment:** Selecione **Docker** (a Render detecta o `Dockerfile` automaticamente).
   - **Instance Type:** Free (ou Starter).

3. **Configure as Variáveis de Ambiente no painel da Render:**
   - Na aba **Environment Variables**, adicione:
     - `TELEGRAM_BOT_TOKEN` = `9224474540:AAFpGj8sBzPUTShYXMOSnu9Bg03TzFR2UUs`
     - `GEMINI_API_KEY` = *Sua chave da API do Gemini*
     - `ALLOWED_TELEGRAM_IDS` = *Seu ID e o da sua esposa*
     - `TIMEZONE` = `America/Sao_Paulo`
     - `PORT` = `8080`

4. **Deploy:**
   - Clique em **Create Web Service**. A Render vai construir a imagem Docker e o servidor de *healthcheck* na porta `8080` garantirá que o serviço seja marcado como saudável (*healthy*) e fique rodando!

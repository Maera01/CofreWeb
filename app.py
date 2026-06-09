from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from functools import wraps
from datetime import timedelta
from collections import defaultdict
import time
import core
from core import init_db

# Inicializa o banco de dados
init_db()

app = Flask(__name__)
import os
app.secret_key = os.environ.get("SECRET_KEY", "cofre-digital-secret-2024")

# ✅ Sessão expira após 30 minutos de inatividade
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
app.config["SESSION_PERMANENT"] = True

# ✅ Proteção contra força bruta
tentativas = defaultdict(list)

def verificar_tentativas(ip):
    agora = time.time()
    tentativas[ip] = [t for t in tentativas[ip] if agora - t < 300]
    if len(tentativas[ip]) >= 5:
        return False
    tentativas[ip].append(agora)
    return True

# ✅ Renova o tempo a cada requisição
@app.before_request
def renovar_sessao():
    session.modified = True


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True})


@app.route("/wake-sw.js")
def wake_sw():
    sw = r"""
const WAKE_TIMEOUT = 900;

function wakingScreen(targetUrl) {
  const safeTarget = JSON.stringify(targetUrl);
  return new Response(`<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cofre Digital - Acordando</title>
<style>
  :root {
    --bg:#0a0a0f; --surface:#111118; --border:#1e1e2e;
    --accent:#4f8ef7; --accent2:#14b8a6; --text:#e2e8f0; --muted:#94a3b8;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body {
    min-height:100vh; display:flex; align-items:center; justify-content:center;
    background:var(--bg); color:var(--text);
    font-family:Arial, Helvetica, sans-serif; overflow:hidden;
  }
  body::before {
    content:""; position:fixed; inset:0;
    background-image:
      linear-gradient(rgba(79,142,247,.05) 1px, transparent 1px),
      linear-gradient(90deg, rgba(79,142,247,.05) 1px, transparent 1px);
    background-size:40px 40px;
    mask-image:radial-gradient(ellipse 75% 75% at 50% 50%, black 25%, transparent 100%);
  }
  .wake {
    position:relative; width:min(420px, 92vw); padding:34px 28px;
    border:1px solid var(--border); border-radius:18px; background:rgba(17,17,24,.92);
    text-align:center; box-shadow:0 28px 90px rgba(0,0,0,.55);
  }
  .vault {
    width:94px; height:94px; margin:0 auto 22px; border-radius:28px;
    display:grid; place-items:center; position:relative;
    background:linear-gradient(145deg, #172033, #101018);
    border:1px solid rgba(79,142,247,.35);
    box-shadow:0 0 36px rgba(79,142,247,.22);
  }
  .vault::before {
    content:""; width:48px; height:48px; border-radius:50%;
    border:7px solid var(--accent); border-top-color:var(--accent2);
    animation:spin 1.1s linear infinite;
  }
  .pulse {
    position:absolute; inset:-12px; border:1px solid rgba(79,142,247,.35);
    border-radius:34px; animation:pulse 1.7s ease-out infinite;
  }
  h1 { font-size:24px; margin-bottom:8px; letter-spacing:.2px; }
  p { color:var(--muted); font-size:14px; line-height:1.55; }
  .dots::after { content:""; animation:dots 1.4s steps(4,end) infinite; }
  .bar {
    height:5px; width:100%; overflow:hidden; border-radius:999px;
    background:#1f2937; margin-top:24px;
  }
  .bar span {
    display:block; width:42%; height:100%; border-radius:999px;
    background:linear-gradient(90deg, var(--accent), var(--accent2));
    animation:slide 1.25s ease-in-out infinite;
  }
  .status { margin-top:14px; font-size:12px; color:#64748b; }
  @keyframes spin { to { transform:rotate(360deg); } }
  @keyframes pulse { to { transform:scale(1.18); opacity:0; } }
  @keyframes slide {
    0% { transform:translateX(-110%); }
    50% { transform:translateX(70%); }
    100% { transform:translateX(250%); }
  }
  @keyframes dots {
    0% { content:""; } 25% { content:"."; } 50% { content:".."; } 75%,100% { content:"..."; }
  }
</style>
</head>
<body>
  <main class="wake">
    <div class="vault"><span class="pulse"></span></div>
    <h1>Acordando o Cofre</h1>
    <p>O servidor gratuito estava em descanso. Estamos reconectando com seguranca<span class="dots"></span></p>
    <div class="bar"><span></span></div>
    <div class="status" id="status">Tentando novamente...</div>
  </main>
  <script>
    const target = ${safeTarget};
    const status = document.getElementById("status");
    let tries = 0;

    async function retry() {
      tries += 1;
      status.textContent = "Tentativa " + tries + " de reconexao";
      try {
        const response = await fetch(target, { cache: "no-store", credentials: "include" });
        if (response.ok || response.redirected) {
          window.location.replace(target);
          return;
        }
      } catch (error) {}
      setTimeout(retry, Math.min(1800 + tries * 400, 5000));
    }
    setTimeout(retry, 800);
  </script>
</body>
</html>`, {
    headers: { "Content-Type": "text/html; charset=utf-8" }
  });
}

self.addEventListener("install", event => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.mode !== "navigate" || request.method !== "GET") return;

  event.respondWith((async () => {
    const network = fetch(request);
    const timeout = new Promise(resolve => {
      setTimeout(() => resolve(wakingScreen(request.url)), WAKE_TIMEOUT);
    });

    try {
      return await Promise.race([network, timeout]);
    } catch (error) {
      return wakingScreen(request.url);
    }
  })());
});
"""
    return Response(
        sw,
        mimetype="application/javascript",
        headers={"Cache-Control": "no-store"}
    )


# ─── DECORADORES ───────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("tipo") != "admin":
            return jsonify({"erro": "Acesso negado"}), 403
        return f(*args, **kwargs)
    return decorated


# ─── LOGIN / LOGOUT ────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    erro = None

    if request.method == "POST":
        usuario  = request.form.get("usuario", "").strip()
        senha    = request.form.get("senha", "")
        s_master = request.form.get("senha_master", "")
        ip       = request.remote_addr

        # ✅ Verifica tentativas de login
        if not verificar_tentativas(ip):
            erro = "Muitas tentativas. Aguarde 5 minutos."
            return render_template("login.html", erro=erro)

        usuarios = core.carregar_usuarios()
        config   = core.carregar_config()

        if usuario not in usuarios:
            erro = "Usuário não encontrado."
        elif usuarios[usuario]["senha"] != core._hash_senha(senha):
            erro = "Senha incorreta."
        else:
            if not config.get("senha_master_hash"):
                core.definir_senha_master(s_master)
            elif not core.verificar_senha_master(s_master):
                erro = "Senha master incorreta."

        if not erro:
            try:
                core.carregar_cofre(s_master, config)

                u = usuarios[usuario]

                session.permanent = True
                session["usuario"]      = usuario
                session["tipo"]         = u["tipo"]
                session["setores"]      = u.get("setores", [])
                session["senha_master"] = s_master

                # ✅ Permissões — admin tem todas automaticamente
                if u["tipo"] == "admin":
                    session["permissoes"] = [
                        "ver", "copiar", "adicionar", "editar", "excluir"
                    ]
                else:
                    session["permissoes"] = u.get("permissoes", [])

                core.registrar_evento(
                    usuario,
                    "LOGIN",
                    f"Usuário '{usuario}' fez login."
                )

                return redirect(url_for("dashboard"))
            except Exception as e:
                erro = str(e)

    return render_template("login.html", erro=erro)


@app.route("/logout")
def logout():
    usuario = session.get("usuario", "desconhecido")
    core.registrar_evento(
        usuario,
        "LOGOUT",
        f"Usuário '{usuario}' saiu do sistema."
    )
    session.clear()
    return redirect(url_for("login"))


# ─── DASHBOARD ─────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    config = core.carregar_config()
    cofre  = core.carregar_cofre(session["senha_master"], config)

    tipo    = session["tipo"]
    setores = config["setores"] if tipo == "admin" else session["setores"]

    contagem = {s: len(cofre["setores"].get(s, [])) for s in setores}

    return render_template(
        "dashboard.html",
        usuario=session["usuario"],
        tipo=tipo,
        setores=setores,
        contagem=contagem
    )


# ─── SETOR ─────────────────────────────────────────────────────────────
@app.route("/setor/<setor>")
@login_required
def setor(setor):
    config = core.carregar_config()
    tipo   = session["tipo"]

    if tipo != "admin" and setor not in session["setores"]:
        return redirect(url_for("dashboard"))

    permissoes = session.get("permissoes", [])

    cofre      = core.carregar_cofre(session["senha_master"], config)
    senhas_raw = cofre["setores"].get(setor, [])

    senhas = []
    for i, s in enumerate(senhas_raw):
        senhas.append({
            "id":      i,
            "servico": s.get("servico", ""),
            "login":   s.get("login", ""),
            "obs":     s.get("obs", "")
        })

    return render_template(
        "setor.html",
        setor=setor,
        senhas=senhas,
        tipo=tipo,
        permissoes=permissoes,
        usuario=session["usuario"]
    )


# ─── API: VER SENHA ────────────────────────────────────────────────────
@app.route("/api/senha/ver/<setor>/<int:index>")
@login_required
def api_ver_senha(setor, index):
    tipo       = session["tipo"]
    permissoes = session.get("permissoes", [])

    if tipo != "admin" and setor not in session["setores"]:
        return jsonify({"erro": "Acesso negado ao setor"}), 403

    if "ver" not in permissoes:
        return jsonify({"erro": "Sem permissão para ver senhas"}), 403

    config = core.carregar_config()
    cofre  = core.carregar_cofre(session["senha_master"], config)
    senhas = cofre["setores"].get(setor, [])

    if index < 0 or index >= len(senhas):
        return jsonify({"erro": "Senha não encontrada"}), 404

    core.registrar_evento(
        session["usuario"],
        "VER SENHA",
        f"Setor: {setor} | Serviço: {senhas[index].get('servico', '')}"
    )

    return jsonify({
        "ok":    True,
        "senha": senhas[index].get("senha", "")
    })


# ─── API: ADICIONAR SENHA ──────────────────────────────────────────────
@app.route("/api/senha/adicionar", methods=["POST"])
@login_required
def api_adicionar_senha():
    if "adicionar" not in session.get("permissoes", []):
        return jsonify({"erro": "Sem permissão para adicionar senhas"}), 403

    data  = request.json
    setor = data.get("setor")

    if session["tipo"] != "admin" and setor not in session["setores"]:
        return jsonify({"erro": "Acesso negado ao setor"}), 403

    if not data.get("servico") or not data.get("login") or not data.get("senha"):
        return jsonify({"erro": "Campos obrigatórios ausentes"}), 400

    config = core.carregar_config()
    cofre  = core.carregar_cofre(session["senha_master"], config)

    cofre["setores"].setdefault(setor, []).append({
        "servico": data["servico"],
        "login":   data["login"],
        "senha":   data["senha"],
        "obs":     data.get("obs", "")
    })

    core.salvar_cofre(cofre["setores"], session["senha_master"])

    core.registrar_evento(
        session["usuario"],
        "CRIAR SENHA",
        f"Setor: {setor} | Serviço: {data['servico']}"
    )

    return jsonify({"ok": True})


# ─── API: EDITAR SENHA ─────────────────────────────────────────────────
@app.route("/api/senha/editar", methods=["POST"])
@login_required
def api_editar_senha():
    if "editar" not in session.get("permissoes", []):
        return jsonify({"erro": "Sem permissão para editar senhas"}), 403

    data  = request.json
    setor = data.get("setor")
    index = int(data.get("id", -1))

    if session["tipo"] != "admin" and setor not in session["setores"]:
        return jsonify({"erro": "Acesso negado ao setor"}), 403

    config = core.carregar_config()
    cofre  = core.carregar_cofre(session["senha_master"], config)
    senhas = cofre["setores"].get(setor, [])

    if index < 0 or index >= len(senhas):
        return jsonify({"erro": "Senha não encontrada"}), 404

    senhas[index]["servico"] = data.get("servico", senhas[index]["servico"])
    senhas[index]["login"]   = data.get("login",   senhas[index]["login"])
    senhas[index]["obs"]     = data.get("obs",     senhas[index].get("obs", ""))

    if data.get("senha"):
        senhas[index]["senha"] = data["senha"]

    cofre["setores"][setor] = senhas
    core.salvar_cofre(cofre["setores"], session["senha_master"])

    core.registrar_evento(
        session["usuario"],
        "EDITAR SENHA",
        f"Setor: {setor} | Serviço: {senhas[index]['servico']}"
    )

    return jsonify({"ok": True})


# ─── API: EXCLUIR SENHA ────────────────────────────────────────────────
@app.route("/api/senha/excluir", methods=["POST"])
@login_required
def api_excluir_senha():
    if "excluir" not in session.get("permissoes", []):
        return jsonify({"erro": "Sem permissão para excluir senhas"}), 403

    data  = request.json
    setor = data.get("setor")
    index = int(data.get("id", -1))

    if session["tipo"] != "admin" and setor not in session["setores"]:
        return jsonify({"erro": "Acesso negado ao setor"}), 403

    config = core.carregar_config()
    cofre  = core.carregar_cofre(session["senha_master"], config)
    senhas = cofre["setores"].get(setor, [])

    if index < 0 or index >= len(senhas):
        return jsonify({"erro": "Senha não encontrada"}), 404

    servico_removido = senhas[index].get("servico", "")
    senhas.pop(index)

    cofre["setores"][setor] = senhas
    core.salvar_cofre(cofre["setores"], session["senha_master"])

    core.registrar_evento(
        session["usuario"],
        "EXCLUIR SENHA",
        f"Setor: {setor} | Serviço: {servico_removido}"
    )

    return jsonify({"ok": True})


# ─── API: LISTAR SETORES ───────────────────────────────────────────────
@app.route("/api/setores")
@login_required
def api_listar_setores():
    config  = core.carregar_config()
    cofre   = core.carregar_cofre(session["senha_master"], config)
    setores = config.get("setores", [])

    resultado = []
    for s in setores:
        qtd = len(cofre["setores"].get(s, []))
        resultado.append({"nome": s, "qtd": qtd})

    return jsonify({"ok": True, "setores": resultado})


# ─── API: CRIAR SETOR ──────────────────────────────────────────────────
@app.route("/api/setor/criar", methods=["POST"])
@login_required
def api_criar_setor():
    if session["tipo"] != "admin":
        return jsonify({"erro": "Acesso negado"}), 403

    data = request.json
    nome = data.get("nome", "").strip()

    if not nome:
        return jsonify({"erro": "Nome do setor inválido."}), 400

    config = core.carregar_config()

    if nome in config.get("setores", []):
        return jsonify({"erro": f"Setor '{nome}' já existe."}), 400

    config.setdefault("setores", []).append(nome)
    core.salvar_config(config)

    core.registrar_evento(
        session["usuario"],
        "CRIAR SETOR",
        f"Setor '{nome}' criado."
    )

    return jsonify({"ok": True})


# ─── API: EXCLUIR SETOR ────────────────────────────────────────────────
@app.route("/api/setor/excluir", methods=["POST"])
@login_required
def api_excluir_setor():
    if session["tipo"] != "admin":
        return jsonify({"erro": "Acesso negado"}), 403

    data = request.json
    nome = data.get("nome", "").strip()

    config = core.carregar_config()
    cofre  = core.carregar_cofre(session["senha_master"], config)

    if nome not in config.get("setores", []):
        return jsonify({"erro": "Setor não encontrado."}), 404

    config["setores"].remove(nome)
    core.salvar_config(config)

    if nome in cofre["setores"]:
        del cofre["setores"][nome]
        core.salvar_cofre(cofre["setores"], session["senha_master"])

    core.registrar_evento(
        session["usuario"],
        "EXCLUIR SETOR",
        f"Setor '{nome}' excluído com todas as suas senhas."
    )

    return jsonify({"ok": True})


# ─── PÁGINA: USUÁRIOS ──────────────────────────────────────────────────
@app.route("/usuarios")
@login_required
@admin_required
def usuarios():
    config  = core.carregar_config()
    lista   = core.carregar_usuarios()
    setores = config.get("setores", [])
    return render_template(
        "usuarios.html",
        usuarios=lista,
        setores=setores,
        usuario_logado=session["usuario"],
        tipo=session["tipo"]
    )


# ─── API: CRIAR USUÁRIO ────────────────────────────────────────────────
@app.route("/api/usuario/criar", methods=["POST"])
@login_required
def api_criar_usuario():
    if session["tipo"] != "admin":
        return jsonify({"erro": "Acesso negado"}), 403

    data       = request.json
    nome       = data.get("nome", "").strip()
    senha      = data.get("senha", "")
    tipo       = data.get("tipo", "usuario")
    setores    = data.get("setores", [])
    permissoes = data.get("permissoes", [])

    if not nome or not senha:
        return jsonify({"erro": "Nome e senha são obrigatórios."}), 400

    usuarios = core.carregar_usuarios()

    if nome in usuarios:
        return jsonify({"erro": f"Usuário '{nome}' já existe."}), 400

    usuarios[nome] = {
        "senha":      core._hash_senha(senha),  # ✅ Hash aqui!
        "tipo":       tipo,
        "setores":    setores    if tipo != "admin" else [],
        "permissoes": permissoes if tipo != "admin" else []
    }

    core.salvar_usuarios(usuarios)

    core.registrar_evento(
        session["usuario"],
        "CRIAR USUÁRIO",
        f"Usuário '{nome}' criado com tipo '{tipo}'."
    )

    return jsonify({"ok": True})


# ─── API: EDITAR USUÁRIO ───────────────────────────────────────────────
@app.route("/api/usuario/editar", methods=["POST"])
@login_required
def api_editar_usuario():
    if session["tipo"] != "admin":
        return jsonify({"erro": "Acesso negado"}), 403

    data       = request.json
    original   = data.get("original", "").strip()
    novo_nome  = data.get("nome", "").strip()
    senha      = data.get("senha", "")
    tipo       = data.get("tipo", "usuario")
    setores    = data.get("setores", [])
    permissoes = data.get("permissoes", [])

    if not novo_nome:
        return jsonify({"erro": "Nome não pode ser vazio."}), 400

    usuarios = core.carregar_usuarios()

    if original not in usuarios:
        return jsonify({"erro": "Usuário não encontrado."}), 404

    if novo_nome != original and novo_nome in usuarios:
        return jsonify({"erro": f"Usuário '{novo_nome}' já existe."}), 400

    dados = usuarios[original]
    dados["tipo"]       = tipo
    dados["setores"]    = setores    if tipo != "admin" else []
    dados["permissoes"] = permissoes if tipo != "admin" else []

    if senha:
        dados["senha"] = core._hash_senha(senha)  # ✅ Hash aqui!

    if novo_nome != original:
        del usuarios[original]
        usuarios[novo_nome] = dados
    else:
        usuarios[original] = dados

    core.salvar_usuarios(usuarios)

    core.registrar_evento(
        session["usuario"],
        "EDITAR USUÁRIO",
        f"Usuário '{original}' editado."
        + (f" → renomeado para '{novo_nome}'." if novo_nome != original else "")
    )

    return jsonify({"ok": True})


# ─── API: EXCLUIR USUÁRIO ──────────────────────────────────────────────
@app.route("/api/usuario/excluir", methods=["POST"])
@login_required
def api_excluir_usuario():
    if session["tipo"] != "admin":
        return jsonify({"erro": "Acesso negado"}), 403

    data = request.json
    nome = data.get("nome", "").strip()

    if nome == session["usuario"]:
        return jsonify({"erro": "Você não pode excluir seu próprio usuário."}), 400

    usuarios = core.carregar_usuarios()

    if nome not in usuarios:
        return jsonify({"erro": "Usuário não encontrado."}), 404

    del usuarios[nome]
    core.salvar_usuarios(usuarios)

    core.registrar_evento(
        session["usuario"],
        "EXCLUIR USUÁRIO",
        f"Usuário '{nome}' excluído."
    )

    return jsonify({"ok": True})


# ─── API: ALTERAR SENHA MASTER ─────────────────────────────────────────
@app.route("/api/senha-master/alterar", methods=["POST"])
@login_required
def api_alterar_senha_master():
    if session["tipo"] != "admin":
        return jsonify({"erro": "Acesso negado"}), 403

    data  = request.json
    atual = data.get("atual", "")
    nova  = data.get("nova", "")

    if not atual or not nova:
        return jsonify({"erro": "Preencha todos os campos."}), 400

    if not core.verificar_senha_master(atual):
        return jsonify({"erro": "Senha master atual incorreta."}), 403

    if len(nova) < 6:
        return jsonify({"erro": "A nova senha deve ter ao menos 6 caracteres."}), 400

    config = core.carregar_config()
    cofre  = core.carregar_cofre(atual, config)

    # ✅ Re-criptografa o cofre com a nova senha
    core.salvar_cofre(cofre["setores"], nova)

    # ✅ Atualiza o hash da nova senha master
    core.definir_senha_master(nova)

    core.registrar_evento(
        session["usuario"],
        "ALTERAR SENHA MASTER",
        "Senha master alterada com sucesso."
    )

    return jsonify({"ok": True})


# ─── API: RENOVAR SESSÃO ───────────────────────────────────────────────
@app.route("/api/sessao/renovar", methods=["POST"])
@login_required
def api_renovar_sessao():
    session.modified = True
    return jsonify({"ok": True})


# ─── AUDITORIA ─────────────────────────────────────────────────────────
@app.route("/auditoria")
@login_required
@admin_required
def auditoria():
    eventos = list(reversed(core.carregar_auditoria()))
    return render_template(
        "auditoria.html",
        eventos=eventos,
        usuario=session["usuario"],
        tipo=session["tipo"]
    )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)

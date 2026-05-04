from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
from datetime import timedelta
import core
from core import init_db

# Inicializa o banco de dados
init_db()

app = Flask(__name__)
app.secret_key = "cofre-digital-secret-2024"

# ✅ Sessão expira após 30 minutos de inatividade
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
app.config["SESSION_PERMANENT"] = True


# ✅ Renova o tempo a cada requisição
@app.before_request
def renovar_sessao():
    session.modified = True


# ─── DECORADORES ───────────────────────────────────────────────────────
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

        usuarios = core.carregar_usuarios()
        config   = core.carregar_config()

        if usuario not in usuarios:
            erro = "Usuário não encontrado."
        elif usuarios[usuario]["senha"] != senha:
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


# ─── DASHBOARD ─────────────────────────────────────────────────────────
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
        "senha":      senha,
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
        dados["senha"] = senha

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

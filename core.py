import json, os, hashlib, base64
from cryptography.fernet import Fernet

DATA_DIR       = os.path.join(os.path.dirname(__file__), "data")
CONFIG_FILE    = os.path.join(DATA_DIR, "cofre_config.json")
COFRE_FILE     = os.path.join(DATA_DIR, "cofre_dados.json")
USUARIOS_FILE  = os.path.join(DATA_DIR, "usuarios.json")
AUDITORIA_FILE = os.path.join(DATA_DIR, "auditoria.json")

SETORES_PADRAO = [
    "Produção", "Qualidade", "Comercial", "Engenharia",
    "RH", "Fiscal", "Assistência Técnica", "Almoxarifado", "Outros"
]

PERMISSOES_TODAS = ["ver", "copiar", "adicionar", "editar", "excluir"]


# ─── HELPERS ───────────────────────────────────────────────────────────

def _read(path, default):
    if not os.path.exists(path):
        _write(path, default)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if d else default
    except:
        return default

def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def _hash(s):
    return hashlib.sha256(s.encode()).hexdigest()

def _fernet_key(s):
    return base64.urlsafe_b64encode(hashlib.sha256(s.encode()).digest())


# ─── CONFIG ────────────────────────────────────────────────────────────

def carregar_config():
    default = {"setores": SETORES_PADRAO, "senha_master_hash": None}
    return _read(CONFIG_FILE, default)

def salvar_config(config: dict):
    """Salva o arquivo de configuração."""
    _write(CONFIG_FILE, config)

def definir_senha_master(nova):
    c = carregar_config()
    c["senha_master_hash"] = _hash(nova)
    salvar_config(c)

def verificar_senha_master(s):
    c = carregar_config()
    if not c.get("senha_master_hash"):
        return False
    return _hash(s) == c["senha_master_hash"]


# ─── COFRE ─────────────────────────────────────────────────────────────

def _cofre_padrao(config):
    return {s: [] for s in config["setores"]}

def carregar_cofre(senha_master, config):
    if config.get("senha_master_hash"):
        if not verificar_senha_master(senha_master):
            raise Exception("Senha master incorreta.")

    if not os.path.exists(COFRE_FILE):
        salvar_cofre(_cofre_padrao(config), senha_master)
        return {"setores": _cofre_padrao(config)}

    try:
        with open(COFRE_FILE, "rb") as f:
            enc = f.read()
        fernet = Fernet(_fernet_key(senha_master))
        dados  = json.loads(fernet.decrypt(enc).decode())
        for s in config["setores"]:
            dados.setdefault(s, [])
        return {"setores": dados}
    except:
        salvar_cofre(_cofre_padrao(config), senha_master)
        return {"setores": _cofre_padrao(config)}

def salvar_cofre(dados, senha_master):
    fernet = Fernet(_fernet_key(senha_master))
    enc    = fernet.encrypt(json.dumps(dados, ensure_ascii=False).encode())
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(COFRE_FILE, "wb") as f:
        f.write(enc)


# ─── USUÁRIOS ──────────────────────────────────────────────────────────

def _usuarios_padrao():
    """Usuário admin padrão com todas as permissões."""
    return {
        "admin": {
            "senha":      "admin123",
            "tipo":       "admin",
            "setores":    [],           # admin acessa todos automaticamente
            "permissoes": []            # admin tem todas automaticamente via código
        }
    }

def carregar_usuarios():
    usuarios = _read(USUARIOS_FILE, _usuarios_padrao())

    # ✅ Garante que todos os usuários tenham o campo permissoes
    atualizado = False
    for nome, u in usuarios.items():
        if "permissoes" not in u:
            u["permissoes"] = [] if u.get("tipo") == "admin" else ["ver", "copiar"]
            atualizado = True
        if "setores" not in u:
            u["setores"] = []
            atualizado = True

    if atualizado:
        salvar_usuarios(usuarios)

    return usuarios

def salvar_usuarios(usuarios: dict):
    """Salva o arquivo de usuários."""
    _write(USUARIOS_FILE, usuarios)

def criar_usuario(username, senha, tipo, setores, permissoes=None):
    u = carregar_usuarios()
    if username in u:
        raise ValueError("Usuário já existe.")
    u[username] = {
        "senha":      senha,
        "tipo":       tipo,
        "setores":    setores    if tipo != "admin" else [],
        "permissoes": permissoes if (tipo != "admin" and permissoes) else []
    }
    salvar_usuarios(u)

def editar_usuario(username, senha, tipo, setores, permissoes=None):
    u = carregar_usuarios()
    if username not in u:
        raise ValueError("Usuário não encontrado.")
    dados = u[username]
    dados["tipo"]       = tipo
    dados["setores"]    = setores    if tipo != "admin" else []
    dados["permissoes"] = permissoes if (tipo != "admin" and permissoes) else []
    if senha:
        dados["senha"] = senha
    u[username] = dados
    salvar_usuarios(u)

def excluir_usuario(username):
    u = carregar_usuarios()
    if username == "admin":
        raise ValueError("Não é permitido excluir o admin.")
    if username not in u:
        raise ValueError("Usuário não encontrado.")
    del u[username]
    salvar_usuarios(u)


# ─── AUDITORIA ─────────────────────────────────────────────────────────

def carregar_auditoria():
    return _read(AUDITORIA_FILE, [])

def registrar_evento(usuario, acao, detalhes):
    from datetime import datetime
    ev = carregar_auditoria()
    ev.append({
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "usuario":   usuario,
        "acao":      acao,
        "detalhes":  detalhes
    })
    _write(AUDITORIA_FILE, ev)

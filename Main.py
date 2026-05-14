import telnetlib
import time
import threading
import getpass
import os

# =========================
# 🔧 CONFIG
# =========================
ADMIN_PASSWORD = "admin123"


# =========================
# ⏳ INPUT COM TIMEOUT
# =========================
def input_timeout(prompt, timeout=180):
    user_input = [None]

    def get_input():
        user_input[0] = input(prompt)

    thread = threading.Thread(target=get_input)
    thread.daemon = True
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        return None
    return user_input[0]


# =========================
# 🔌 TELNET + PAGINAÇÃO
# =========================
def send_command(tn, cmd, delay=1, expect_confirm=False):
    tn.write((cmd + "\n").encode())
    time.sleep(delay)

    output = ""

    while True:
        chunk = tn.read_very_eager().decode(errors="ignore")
        output += chunk

        # 📄 Trata paginação (--More--)
        if any(x in chunk for x in ["More", "--More--", "---- More ----"]):
            tn.write(b" ")
            time.sleep(0.5)
        else:
            break

    # 🔥 Trata confirmação da OLT (FORA do loop)
    if expect_confirm:
        if any(x in output.lower() for x in ["y/n", "yes/no", "[y/n]"]):
            tn.write(b"yes\n")

        # ⏳ espera a OLT processar o comando
            time.sleep(2)

        # 🔁 lê várias vezes pra capturar toda resposta
        for _ in range(5):
            chunk = tn.read_very_eager().decode(errors="ignore")
            if chunk:
                output += chunk
            time.sleep(0.5)
    return output

def conectar_olt(ip):
    tn = telnetlib.Telnet(ip, 23, timeout=10)

    tn.read_until(b"Username:")
    tn.write(b"valenet\n")

    tn.read_until(b"Password:")
    tn.write(b"P@w3r\n")

    tn.read_until(b"#")

    # tenta desativar paginação
    send_command(tn, "terminal length 0")

    print("✅ Conectado na OLT")
    return tn


# =========================
# 🔍 ONU
# =========================
def buscar_onu(tn, sn):
    output = send_command(tn, f"show gpon onu by sn {sn}")

    for linha in output.splitlines():
        if "gpon-onu_" in linha:
            for palavra in linha.split():
                if "gpon-onu_" in palavra:
                    return palavra
    return None


def separar_onu(onu):
    parte = onu.replace("gpon-onu_", "")
    pon = parte.split(":")[0]
    onu_id = parte.split(":")[1]
    return pon, onu_id


# =========================
# 🔍 CONSULTAS
# =========================
def status_onu(tn, pon, onu_id):
    return send_command(tn, f"show gpon onu state gpon-olt_{pon} {onu_id}")


def historico_onu(tn, onu):
    return send_command(tn, f"show gpon onu detail-info {onu}")


def sinal_onu(tn, onu):
    return send_command(tn, f"show pon power attenuation {onu}")


def script_onu(tn, onu):
    return send_command(tn, f"show onu running config {onu}")


def mac_onu(tn, onu):
    return send_command(tn, f"show mac gpon onu {onu}")


def vlan_translate(tn, onu):
    return send_command(tn, f"show running-config interface {onu}")


# =========================
# ⚙️ PROCEDIMENTOS
# =========================
def reboot_onu(tn, onu):
    print("\n===== REBOOT ONU =====")
    print("Comandos executados:")
    print("configure terminal")
    print(f"pon-onu-mng {onu}")
    print("reboot\n")

    output = ""

    output += send_command(tn, "configure terminal")
    output += send_command(tn, f"pon-onu-mng {onu}")
    output += send_command(tn, "reboot", expect_confirm=True)

    return output

def reset_onu(tn, pon, onu_id):
    print("\n===== RESET ONU =====")
    print("Comandos executados:")
    print("configure terminal")
    print(f"{pon}:{onu_id}")
    print("restore factory\n")

    # ⚠️ Confirmação do usuário (mais rigorosa)
    confirm = input("⚠️ ATENÇÃO: Isso vai resetar a ONU para padrão de fábrica. Deseja continuar? (s/n): ")
    if confirm.lower() != "s":
        print("❌ Operação cancelada.")
        return ""

    output = ""

    try:
        output += send_command(tn, "configure terminal")
        time.sleep(1)

        output += send_command(tn, f"{pon}:{onu_id}")
        time.sleep(1)

        # 🔥 Aqui entra confirmação automática da OLT
        output += send_command(tn, "restore factory", expect_confirm=True)
        time.sleep(2)

        print("✅ Reset executado com sucesso!")

    except Exception as e:
        print("❌ Erro ao executar reset:", e)

    return output


def deletar_onu(tn, pon, onu_id):
    print("\n===== EXCLUSÃO ONU =====")
    print("Comandos executados:")
    print("configure terminal")
    print(f"interface gpon-olt_{pon}")
    print(f"no onu {onu_id}")
    print("end\n")

    output = ""
    output += send_command(tn, "configure terminal")
    output += send_command(tn, f"interface gpon-olt_{pon}")
    output += send_command(tn, f"no onu {onu_id}")
    output += send_command(tn, "end")

    return output

def gerencia_zte(tn, onu):
    print("\n===== ATIVAR GERÊNCIA =====")
    print("Comandos executados:")
    print("configure terminal")
    print(f"pon-onu-mng {onu}")
    print("security-mgmt 1 state enable mode forward ingress-type wan")
    print("end\n")

    output = ""
    output += send_command(tn, "configure terminal")
    output += send_command(tn, f"pon-onu-mng {onu}")
    output += send_command(tn, "security-mgmt 1 state enable mode forward ingress-type wan")
    output += send_command(tn, "end")

    return output


# =========================
# 🔐 AUTENTICAÇÃO
# =========================
def autenticar_admin():
    for _ in range(3):
        tentativa = getpass.getpass("Senha admin: ")
        if tentativa == ADMIN_PASSWORD:
            print("✅ Acesso autorizado")
            return True
        else:
            print("❌ Senha incorreta")

    print("⛔ Acesso bloqueado")
    return False


# =========================
# 🧹 LIMPAR TELA
# =========================
def limpar():
    os.system("cls")


# =========================
# ⚙️ SUBMENU
# =========================
def menu_procedimentos(tn, onu, pon, onu_id):
    while True:
        limpar()
        print("⚙️ ===== PROCEDIMENTOS ===== ⚙️")
        print("1 - Reboot ONU")
        print("2 - Reset ONU")
        print("3 - Excluir ONU")
        print("4 - Ativar Gerência")
        print("0 - Voltar")

        op = input_timeout("\nEscolha: ", 180)

        if op is None:
            print("\n⏳ Sessão encerrada por inatividade")
            tn.close()
            exit()

        if op == "1":
            if input("Confirmar reboot? (s/n): ").lower() == "s":
                print(reboot_onu(tn, onu))

        elif op == "2":
            if input("Confirmar reset? (s/n): ").lower() == "s":
                print(reset_onu(tn, pon, onu_id))

        elif op == "3":
            if input("⚠️ Confirmar EXCLUSÃO? (s/n): ").lower() == "s":
                print(deletar_onu(tn, pon, onu_id))

        elif op == "4":
            print(gerencia_zte(tn, onu))

        elif op == "0":
            break

        input("\nENTER para continuar...")


# =========================
# 📋 MENU PRINCIPAL
# =========================
def menu(tn, onu):
    pon, onu_id = separar_onu(onu)

    while True:
        limpar()

        print("===== MENU =====")
        print(f"ONU: {onu}")
        print(f"PON: {pon} | ID: {onu_id}")

        print("\n1 - Status")
        print("2 - Histórico")
        print("3 - Sinal")
        print("4 - Script ONU")
        print("5 - MAC")
        print("6 - VLAN Translate")
        print("7 - Procedimentos ⚙️")
        print("0 - Sair")

        op = input_timeout("\nEscolha: ", 180)

        if op is None:
            print("\n⏳ Sessão encerrada por inatividade")
            tn.close()
            break

        limpar()

        if op == "1":
            print(status_onu(tn, pon, onu_id))

        elif op == "2":
            print(historico_onu(tn, onu))

        elif op == "3":
            print(sinal_onu(tn, onu))

        elif op == "4":
            print(script_onu(tn, onu))

        elif op == "5":
            print(mac_onu(tn, onu))

        elif op == "6":
            print(vlan_translate(tn, onu))

        elif op == "7":
            if autenticar_admin():
                menu_procedimentos(tn, onu, pon, onu_id)

        elif op == "0":
            tn.close()
            print("Encerrado.")
            break

        else:
            print("Opção inválida")

        input("\nENTER para continuar...")


# =========================
# 🚀 MAIN
# =========================
if __name__ == "__main__":
    ip = input("IP da OLT: ")
    sn = input("SN da ONT: ")

    tn = conectar_olt(ip)

    onu = buscar_onu(tn, sn)

    if not onu:
        print("ONU não encontrada")
    else:
        menu(tn, onu)

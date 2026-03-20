DEEPSEEK_CLOUD_AGENT.PY

#!/usr/bin/env python3
"""
Agente ROS 2 con DeepSeek V3 via OpenRouter (Nube)
---------------------------------------------------
Recibe comandos en lenguaje natural y los convierte
en comandos de terminal ROS 2 para controlar el robot.

Uso:
    export OPENROUTER_API_KEY="tu_api_key"
    python3 deepseek_cloud_agent.py
"""

import os
import re
import subprocess
import sys
import requests
import json

# ── Configuración ────────────────────────────────────────────────────────────

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"
MODEL              = "deepseek/deepseek-chat"   # DeepSeek V3

# Namespace y tópicos del robot
ROBOT_NAMESPACE    = "/fastbot55"
CMD_VEL_TOPIC      = "cmd_vel"
MSG_TYPE           = "geometry_msgs/msg/Twist"

# Ruta de instalación de ROS 2 Humble
ROS2_SETUP         = "/opt/ros/humble/setup.bash"

# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""Eres un experto en ROS 2 Humble y robótica móvil.
Tu única función es convertir comandos en lenguaje natural a comandos de terminal ROS 2.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con el comando de terminal. Sin explicaciones, sin bloques de código, sin markdown.
2. No uses backticks (```), ni comillas al inicio/fin de la respuesta.
3. El comando debe publicar en el tópico: {CMD_VEL_TOPIC}
4. Usa el tipo de mensaje: {MSG_TYPE}
5. Para movimiento usa los campos: linear.x (adelante/atrás) y angular.z (rotación).
6. Usa --once para publicar un solo mensaje.
7. Si el comando no es de movimiento de robot, responde exactamente: COMANDO_INVALIDO

EJEMPLOS:
Usuario: muévete hacia adelante a velocidad 0.3
Respuesta: ros2 topic pub --once {CMD_VEL_TOPIC} {MSG_TYPE} "{{linear: {{x: 0.3, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}"

Usuario: gira a la izquierda
Respuesta: ros2 topic pub --once {CMD_VEL_TOPIC} {MSG_TYPE} "{{linear: {{x: 0.0, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.5}}}}"

Usuario: detente
Respuesta: ros2 topic pub --once {CMD_VEL_TOPIC} {MSG_TYPE} "{{linear: {{x: 0.0, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}"

Usuario: retrocede a velocidad 0.1
Respuesta: ros2 topic pub --once {CMD_VEL_TOPIC} {MSG_TYPE} "{{linear: {{x: -0.1, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}"
"""

# ── Funciones Principales ────────────────────────────────────────────────────

def call_deepseek_api(user_command: str) -> str:
    """Llama a la API de DeepSeek V3 via OpenRouter y retorna el comando ROS 2."""
    if not OPENROUTER_API_KEY:
        raise EnvironmentError(
            "❌ No se encontró OPENROUTER_API_KEY.\n"
            "   Ejecuta: export OPENROUTER_API_KEY='tu_api_key'"
        )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://github.com/ros2-deepseek-agent",
        "X-Title":       "ROS2 DeepSeek Agent",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_command},
        ],
        "temperature": 0.1,   # Baja temperatura → respuestas más deterministas
        "max_tokens":  200,
    }

    print(f"🌐 Consultando DeepSeek V3 (OpenRouter)...")
    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    data    = response.json()
    content = data["choices"][0]["message"]["content"]
    return content.strip()


def clean_ros2_command(raw_output: str) -> str | None:
    """
    Limpia la respuesta del LLM y extrae solo el comando ros2 válido.
    Retorna None si no se encontró un comando válido.
    """
    if "COMANDO_INVALIDO" in raw_output:
        return None

    # Eliminar bloques de código markdown
    cleaned = re.sub(r"```[a-z]*\n?", "", raw_output)
    cleaned = re.sub(r"```",           "", cleaned)

    # Buscar línea que empiece con 'ros2'
    for line in cleaned.splitlines():
        line = line.strip()
        if line.startswith("ros2"):
            return line

    return None


def execute_ros2_command(command: str) -> bool:
    """
    Ejecuta el comando ROS 2 en un subproceso con el entorno de ROS 2 cargado.
    Retorna True si fue exitoso.
    """
    # Construir el script de shell que hace source y ejecuta el comando
    shell_script = f"source {ROS2_SETUP} && {command}"

    print(f"\n🤖 Ejecutando: {command}")
    print("─" * 60)

    result = subprocess.run(
        ["bash", "-c", shell_script],
        capture_output=False,   # Mostrar output en tiempo real
        text=True,
    )

    if result.returncode == 0:
        print("✅ Comando ejecutado exitosamente.")
        return True
    else:
        print(f"❌ Error al ejecutar el comando (código: {result.returncode})")
        return False


def process_natural_language_command(user_input: str) -> None:
    """Pipeline completo: texto → LLM → comando ROS 2 → ejecución."""
    print(f"\n📝 Comando recibido: '{user_input}'")
    print("─" * 60)

    # 1. Llamar al LLM
    try:
        raw_response = call_deepseek_api(user_input)
    except requests.RequestException as e:
        print(f"❌ Error de red al llamar a la API: {e}")
        return
    except EnvironmentError as e:
        print(e)
        return

    print(f"🧠 Respuesta del LLM: {raw_response}")

    # 2. Limpiar y validar el comando
    ros2_command = clean_ros2_command(raw_response)

    if ros2_command is None:
        print("⚠️  No se pudo extraer un comando ROS 2 válido.")
        print("   Verifica que tu solicitud sea un comando de movimiento de robot.")
        return

    # 3. Ejecutar el comando
    execute_ros2_command(ros2_command)


# ── Interfaz de Usuario ──────────────────────────────────────────────────────

def run_interactive_mode() -> None:
    """Modo interactivo: el usuario escribe comandos en un bucle."""
    print("=" * 60)
    print("  🤖 Agente ROS 2 con DeepSeek V3 (Cloud)")
    print(f"  Tópico: {CMD_VEL_TOPIC}")
    print("  Escribe 'salir' para terminar.")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Agente detenido.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("salir", "exit", "quit"):
            print("👋 Agente detenido.")
            break

        process_natural_language_command(user_input)


def run_single_command(command: str) -> None:
    """Ejecuta un único comando pasado como argumento de línea de comandos."""
    process_natural_language_command(command)


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Modo single-command: python3 agent.py "muévete adelante"
        run_single_command(" ".join(sys.argv[1:]))
    else:
        # Modo interactivo
        run_interactive_mode()
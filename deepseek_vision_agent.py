#!/usr/bin/env python3
"""
Agente ROS 2 con Gemini Flash + DeepSeek V3 (dos pasos)
--------------------------------------------------------
Paso 1: Gemini 2.0 Flash describe la escena desde la cámara.
Paso 2: DeepSeek V3 convierte (escena + comando) en ros2 topic pub.

Requisitos:
    pip3 install --user requests Pillow

Variables de entorno:
    export OPENROUTER_API_KEY="sk-or-v1-..."   # para DeepSeek
    export GEMINI_API_KEY="AIza..."             # para visión (aistudio.google.com)

Uso:
    python3 deepseek_vision_agent.py
    python3 deepseek_vision_agent.py "avanza despacio"
"""

import os
import re
import base64
import subprocess
import sys
import struct
import io
import requests
from PIL import Image as PILImage

# ── Configuración ────────────────────────────────────────────────────────────

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"
PLANNER_MODEL      = "deepseek/deepseek-chat"

GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

CMD_VEL_TOPIC      = "cmd_vel"
MSG_TYPE           = "geometry_msgs/msg/Twist"
ROS2_SETUP         = "/opt/ros/humble/setup.bash"
CAMERA_TOPIC       = "/camera/image_raw"   # ajusta si tu namespace es diferente

# ── Prompts ──────────────────────────────────────────────────────────────────

VLM_PROMPT = (
    "Eres el sistema de visión de un robot móvil. "
    "Describe la escena en español en máximo 2 oraciones. "
    "Incluye: obstáculos visibles, distancias aproximadas y espacio libre para navegar. "
    "Sé directo y concreto pero específico. Ejemplo: "
    "'Hay una pared a aproximadamente 0.5 m al frente. "
    "El pasillo libre está a la derecha.'"
)

PLANNER_SYSTEM = f"""Eres un experto en ROS 2 Humble y robótica móvil.
Tu única función es convertir comandos en lenguaje natural a comandos de terminal ROS 2,
considerando el contexto visual del robot.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con el comando de terminal. Sin explicaciones ni markdown.
2. No uses backticks, ni comillas al inicio/fin de la respuesta.
3. El comando debe publicar en el tópico: {CMD_VEL_TOPIC}
4. Usa el tipo de mensaje: {MSG_TYPE}
5. Usa linear.x (adelante/atrás) y angular.z (rotación).
6. Usa --once para publicar un solo mensaje.
7. Si el contexto visual indica un obstáculo peligroso (<0.3 m) en la dirección del comando,
   genera el comando de detención en su lugar y omite el movimiento solicitado o ejecuta un comando para esquivarlo.
8. Si el contexto visual dice "sin información visual disponible", ignóralo y ejecuta
   el comando normalmente.
9. Si el comando no es de movimiento de robot, responde exactamente: COMANDO_INVALIDO

EJEMPLOS:
Usuario: [Escena: pasillo libre al frente] muévete hacia adelante
Respuesta: ros2 topic pub --once {CMD_VEL_TOPIC} {MSG_TYPE} "{{linear: {{x: 0.3, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}"

Usuario: [Escena: pared a 0.2 m al frente] muévete hacia adelante
Respuesta: ros2 topic pub --once {CMD_VEL_TOPIC} {MSG_TYPE} "{{linear: {{x: 0.0, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}"

Usuario: [Escena: espacio libre] gira a la izquierda
Respuesta: ros2 topic pub --once {CMD_VEL_TOPIC} {MSG_TYPE} "{{linear: {{x: 0.0, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.5}}}}"

Usuario: [Escena: sin obstáculos] detente
Respuesta: ros2 topic pub --once {CMD_VEL_TOPIC} {MSG_TYPE} "{{linear: {{x: 0.0, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}"

Usuario: [Escena: sin información visual disponible] avanza
Respuesta: ros2 topic pub --once {CMD_VEL_TOPIC} {MSG_TYPE} "{{linear: {{x: 0.3, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}"
"""

# ── Captura de frame ─────────────────────────────────────────────────────────

def capture_frame_from_ros() -> bytes | None:
    """
    Captura un frame suscribiéndose directamente al tópico con un nodo
    rclpy de un solo disparo. Devuelve los bytes JPEG o None si falla.
    """
    node_script = f'''
import sys, struct, rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

class FrameCapture(Node):
    def __init__(self):
        super().__init__("frame_capture")
        self.frame = None
        self.create_subscription(Image, "{CAMERA_TOPIC}", self.cb, 1)

    def cb(self, msg):
        self.frame = msg
        raise SystemExit

node = None
try:
    rclpy.init()
    node = FrameCapture()
    rclpy.spin(node)
except SystemExit:
    pass

if node is None or node.frame is None:
    sys.exit(1)

msg = node.frame
sys.stdout.buffer.write(struct.pack("II", msg.width, msg.height) + bytes(msg.data))
node.destroy_node()
rclpy.shutdown()
'''

    script_path = "/tmp/_frame_capture.py"
    with open(script_path, "w") as f:
        f.write(node_script)

    result = subprocess.run(
        ["bash", "-c", f"source {ROS2_SETUP} && python3 {script_path}"],
        capture_output=True,
        timeout=10,
    )

    if result.returncode != 0 or len(result.stdout) < 8:
        print("⚠️  No se pudo capturar frame de la cámara.")
        print(f"   Verifica: ros2 topic echo {CAMERA_TOPIC} --once")
        return None

    width, height = struct.unpack("II", result.stdout[:8])
    raw_bytes = result.stdout[8:]

    try:
        img = PILImage.frombytes("RGB", (width, height), raw_bytes)
        img = img.resize((640, 360), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()
    except Exception as e:
        print(f"⚠️  Error construyendo imagen: {e}")
        return None

# ── Paso 1: visión (Gemini) ──────────────────────────────────────────────────

def describe_scene(image_bytes: bytes) -> str:
    """Envía el frame a Gemini 2.0 Flash y retorna la descripción de la escena."""
    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "❌ No se encontró GEMINI_API_KEY.\n"
            "   Obtén una gratis en https://aistudio.google.com\n"
            "   Luego: export GEMINI_API_KEY='AIza...'"
        )

    b64 = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                {"text": VLM_PROMPT},
            ]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 500,
        },
    }

    print("👁️  Analizando escena con Gemini 2.0 Flash...")
    response = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    description = (
        response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    )
    print(f"🗺️  Escena: {description}")
    return description

# ── Paso 2: planificación (DeepSeek) ────────────────────────────────────────

def plan_command(user_input: str, scene: str) -> str:
    """Envía (escena + comando) a DeepSeek y retorna el comando ROS 2."""
    if not OPENROUTER_API_KEY:
        raise EnvironmentError(
            "❌ No se encontró OPENROUTER_API_KEY.\n"
            "   Ejecuta: export OPENROUTER_API_KEY='sk-or-v1-...'"
        )

    payload = {
        "model": PLANNER_MODEL,
        "messages": [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user",   "content": f"[Escena: {scene}] {user_input}"},
        ],
        "temperature": 0.1,
        "max_tokens":  200,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://github.com/ros2-vision-agent",
        "X-Title":       "ROS2 Vision Agent",
    }

    print(f"🧠 Planificando con {PLANNER_MODEL}...")
    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"].strip()

# ── Ejecución ROS 2 ──────────────────────────────────────────────────────────

def clean_ros2_command(raw: str) -> str | None:
    """Extrae el comando ros2 limpio de la respuesta del LLM."""
    if "COMANDO_INVALIDO" in raw:
        return None

    cleaned = re.sub(r"```[a-z]*\n?", "", raw)
    cleaned = re.sub(r"```", "", cleaned)

    for line in cleaned.splitlines():
        line = line.strip()
        if line.startswith("ros2"):
            return line
    return None


def execute_ros2_command(command: str) -> bool:
    """Ejecuta el comando ROS 2 con el entorno de Humble cargado."""
    print(f"\n🤖 Ejecutando: {command}")
    print("─" * 60)

    result = subprocess.run(
        ["bash", "-c", f"source {ROS2_SETUP} && {command}"],
        text=True,
    )

    if result.returncode == 0:
        print("✅ Comando ejecutado exitosamente.")
        return True
    else:
        print(f"❌ Error al ejecutar el comando (código: {result.returncode})")
        return False

# ── Pipeline principal ───────────────────────────────────────────────────────

def process_command(user_input: str) -> None:
    print(f"\n📝 Comando recibido: '{user_input}'")
    print("─" * 60)

    # Paso 1 — visión
    image_bytes = capture_frame_from_ros()
    if image_bytes:
        try:
            scene_description = describe_scene(image_bytes)
        except (requests.RequestException, EnvironmentError) as e:
            print(f"⚠️  Error en VLM, continuando sin contexto visual: {e}")
            scene_description = "sin información visual disponible"
    else:
        scene_description = "sin información visual disponible"

    # Paso 2 — planificación
    try:
        raw_response = plan_command(user_input, scene_description)
    except (requests.RequestException, EnvironmentError) as e:
        print(f"❌ Error al llamar a DeepSeek: {e}")
        return

    print(f"💬 Respuesta DeepSeek: {raw_response}")

    # Paso 3 — ejecución
    ros2_command = clean_ros2_command(raw_response)
    if ros2_command is None:
        print("⚠️  Comando no válido o movimiento bloqueado por obstáculo.")
        return

    execute_ros2_command(ros2_command)

# ── Interfaz de usuario ──────────────────────────────────────────────────────

def run_interactive() -> None:
    print("=" * 60)
    print("  🤖 Agente ROS 2 — Gemini Flash + DeepSeek V3")
    print(f"  VLM    : Gemini 2.0 Flash")
    print(f"  Planner: {PLANNER_MODEL}")
    print(f"  Cámara : {CAMERA_TOPIC}")
    print(f"  Tópico : {CMD_VEL_TOPIC}")
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

        process_command(user_input)


def run_single(command: str) -> None:
    process_command(command)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_single(" ".join(sys.argv[1:]))
    else:
        run_interactive()
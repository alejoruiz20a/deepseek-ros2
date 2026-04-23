# 🤖 Agente ROS 2 + DeepSeek

Sistema de control de un TurtleBot3 Waffle en Gazebo mediante lenguaje natural. El usuario escribe un comando ("avanza", "gira a la izquierda") y un LLM lo convierte en un `ros2 topic pub` que se ejecuta directamente. Todo corre en la nube: **DeepSeek V3** vía OpenRouter para la planificación de comandos, y **Gemini 2.5 Flash** vía Google AI Studio para el análisis visual (variante con visión). Ambas APIs tienen tier gratuito y no requieren tarjeta de crédito.

Dos variantes disponibles:

| Agente | Archivo | Descripción |
|---|---|---|
| Solo texto | `deepseek_cloud_agent.py` | Convierte comandos de texto en movimientos ROS 2 |
| Texto + visión | `deepseek_vision_agent.py` | Además analiza la cámara del robot antes de actuar |

---

## Requisitos Previos

- Windows 10/11 con WSL2
- Ubuntu 22.04 en WSL2
- GPU NVIDIA con drivers actualizados

---

## Paso 1: Instalar ROS 2 Humble

```bash
sudo apt update && sudo apt install -y software-properties-common curl

sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
     -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
     http://packages.ros.org/ros2/ubuntu jammy main" \
     | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update
sudo apt install -y ros-humble-desktop python3-colcon-common-extensions

echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

---

## Paso 2: Instalar TurtleBot3 y Gazebo

```bash
sudo apt install -y gazebo ros-humble-gazebo-ros-pkgs
sudo apt install -y ros-humble-turtlebot3 ros-humble-turtlebot3-gazebo

echo 'export TURTLEBOT3_MODEL=waffle' >> ~/.bashrc
source ~/.bashrc
```

---

## Paso 3: Crear el proyecto

```bash
mkdir -p ~/ros2_deepseek_agent
cd ~/ros2_deepseek_agent
```

Copia aquí los archivos del agente que vayas a usar.

---

## Paso 4: Configurar API keys

### OpenRouter (requerido por ambos agentes)

Regístrate en [openrouter.ai](https://openrouter.ai) y copia tu API key (empieza con `sk-or-v1-...`).

```bash
echo 'export OPENROUTER_API_KEY="sk-or-v1-xxxx"' >> ~/.bashrc
source ~/.bashrc
```

### Gemini (solo para `deepseek_vision_agent.py`)

Crea una API key gratuita en [aistudio.google.com](https://aistudio.google.com) → **Get API key** → **Create API key**.

```bash
echo 'export GEMINI_API_KEY="AIza..."' >> ~/.bashrc
source ~/.bashrc
```

---

## Paso 5: Instalar dependencias Python

### Para `deepseek_cloud_agent.py`

```bash
pip3 install --user requests
```

### Para `deepseek_vision_agent.py`

```bash
pip3 install --user requests Pillow
```

---

## 🚀 Uso diario

### Terminal 1 — Gazebo (igual para ambos agentes)

```bash
source /opt/ros/humble/setup.bash
export TURTLEBOT3_MODEL=waffle
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py
```

> Si Gazebo abre sin el robot, espera a ver `Loaded world` en la consola y luego ejecuta en otra terminal:
> ```bash
> source /opt/ros/humble/setup.bash
> ros2 run gazebo_ros spawn_entity.py \
>   -entity waffle \
>   -file /opt/ros/humble/share/turtlebot3_gazebo/models/turtlebot3_waffle/model.sdf \
>   -x -2.0 -y -0.5 -z 0.01
> ```

---

### Agente de texto — `deepseek_cloud_agent.py`

Convierte comandos en lenguaje natural directamente en movimientos, sin usar la cámara.

**Terminal 2:**
```bash
source /opt/ros/humble/setup.bash
cd ~/ros2_deepseek_agent
python3 deepseek_cloud_agent.py
```

**Terminal 3 — monitor (opcional):**
```bash
source /opt/ros/humble/setup.bash
ros2 topic echo /cmd_vel
```

---

### Agente con visión — `deepseek_vision_agent.py`

Antes de ejecutar cada comando, captura un frame de la cámara y lo analiza con Gemini 2.5 Flash para describir la escena. DeepSeek usa esa descripción para decidir si el movimiento es seguro.

**Terminal 2:**
```bash
source /opt/ros/humble/setup.bash
cd ~/ros2_deepseek_agent
python3 deepseek_vision_agent.py
```

**Terminal 3 — verificar tópico de cámara (primera vez):**
```bash
source /opt/ros/humble/setup.bash
ros2 topic list | grep image
```

El tópico por defecto es `/camera/image_raw`. Si el tuyo es diferente (por ejemplo `/fastbot55/camera/image_raw`), actualiza la variable `CAMERA_TOPIC` al inicio de `deepseek_vision_agent.py`.

---

## 📋 Comandos que acepta el robot

| Acción | Ejemplo |
|---|---|
| Adelante | `"muévete hacia adelante"`, `"adelante a velocidad 0.3"` |
| Atrás | `"retrocede"`, `"retrocede a velocidad 0.1"` |
| Rotar | `"gira a la izquierda"`, `"gira a la derecha"` |
| Combinado | `"avanza girando a la izquierda"` |
| Detener | `"detente"`, `"para"`, `"stop"` |

### ⚙️ Velocidades recomendadas (Waffle)

- `linear.x` → 0.1 a 0.5 m/s
- `angular.z` → 0.5 a 1.0 rad/s

---

## 🔍 Diferencias entre agentes

```
deepseek_cloud_agent.py
    usuario escribe comando
        → DeepSeek genera ros2 topic pub
            → robot se mueve

deepseek_vision_agent.py
    usuario escribe comando
        → captura frame de /camera/image_raw
            → Gemini 2.5 Flash describe la escena
                → DeepSeek genera ros2 topic pub (considerando la escena)
                    → robot se mueve
```

El agente con visión bloquea automáticamente movimientos hacia obstáculos detectados a menos de 0.3 m. Si la cámara no está disponible, continúa como el agente de texto.
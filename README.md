# 🤖 Agente ROS 2 + DeepSeek — Instalación

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

## Paso 3: Instalar Dependencias del Agente

```bash
pip3 install --user requests
```

---

## Paso 4: Configurar API Key de OpenRouter

Regístrate en [openrouter.ai](https://openrouter.ai) y copia tu API key (empieza con `sk-or-v1-...`)

```bash
echo 'export OPENROUTER_API_KEY="sk-or-v1-xxxx"' >> ~/.bashrc
source ~/.bashrc
```

---

## Paso 5: Crear el Proyecto

```bash
mkdir -p ~/ros2_deepseek_agent
cd ~/ros2_deepseek_agent
```

> Copia aquí el archivo `deepseek_cloud_agent.py`

---

## 🚀 Uso Diario (3 Terminales)

### Terminal 1 — Gazebo
```bash
source /opt/ros/humble/setup.bash
ros2 launch turtlebot3_gazebo turtlebot3_world.launch.py
```

### Terminal 2 — Agente DeepSeek
```bash
source /opt/ros/humble/setup.bash
cd ~/ros2_deepseek_agent
python3 deepseek_cloud_agent.py
```

### Terminal 3 — Monitor (opcional)
```bash
source /opt/ros/humble/setup.bash
ros2 topic echo /cmd_vel
```

---

## 📋 Comandos que Acepta el Robot

| Acción | Ejemplo |
|---|---|
| Adelante | `"muévete hacia adelante"`, `"adelante a velocidad 0.3"` |
| Atrás | `"retrocede"`, `"retrocede a velocidad 0.1"` |
| Rotar | `"gira a la izquierda"`, `"gira a la derecha"` |
| Combinado | `"avanza girando a la izquierda"` |
| Detener | `"detente"`, `"para"`, `"stop"` |

### ⚙️ Velocidades Recomendadas (Waffle)
- `linear.x` → 0.1 a 0.5 m/s
- `angular.z` → 0.5 a 1.0 rad/s
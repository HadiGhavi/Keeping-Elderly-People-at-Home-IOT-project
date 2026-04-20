# 🏥 Keeping Elderly People at Home

> **Continuous health monitoring and real-time intervention for a safer, independent life.**

This project is a state-of-the-art IoT ecosystem designed to bridge the gap between elderly patients and healthcare providers. By leveraging **XGBoost-based temporal classification**, the system monitors vital signs in real-time, detects anomalies with high precision, and orchestrates notifications via Telegram to ensure timely medical attention.

---

## ✨ Key Features

*   **Real-time Vital Tracking:** Continuous monitoring of Heart Rate, SpO2, and Body Temperature.
*   **Intelligent Alerting:** Two-stage alert system (Warning/Critical) powered by Machine Learning.
*   **Dual-Interface Access:**
    *   **Telegram Bot:** Conversational interface for patients to receive alerts and check status.
    *   **Admin Dashboard:** High-level overview for admins to manage the system users.
*   **Microservices Architecture:** Fully containerized services for scalability and fault tolerance.
*   **Automated Retraining:** The system periodically retrains on historical data to adapt to individual patient baselines.

---

## 🏗️ Technical Architecture

The platform operates as a distributed system of specialized microservices:

| Service | Responsibility |
| :--- | :--- |
| **Catalog Service** | Central registry for system configuration, user data, and device mapping. |
| **Monitor Service** | Collects raw sensor data from IoT devices and publishes to the MQTT broker. |
| **Data Ingestion** | The brain of the system. Performs real-time classification and manages model retraining. |
| **Notification** | Orchestrates alerts across different channels based on detected health states. |
| **Telegram Bot** | The primary user interface for real-time interaction and manual status checks. |
| **Database Adapter** | Abstraction layer for persistent storage of health metrics and device logs. |
| **Admin Panel** | Web interface for system administration and doctor-patient mapping. |

---

## 🛠️ Tech Stack

*   **Language:** Python 3.11+
*   **ML Framework:** XGBoost, Scikit-Learn (Joblib for serialization)
*   **Messaging:** MQTT (Paho-MQTT) via HiveMQ Broker
*   **Infrastructure:** Docker & Docker Compose
*   **API/Web:** CherryPy, Requests
*   **Communication:** Telegram Bot API (python-telegram-bot)

---

## 🚀 Getting Started

### Prerequisites
*   **Docker & Docker Compose** installed.
*   **Telegram Bot Token** (obtainable via [@BotFather](https://t.me/botfather)).

### Installation & Deployment
1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/HadiGhavi/Keeping-Elderly-People-at-Home-IOT-project.git
    cd Keeping-Elderly-People-at-Home-IOT-project
    ```

2.  **Configuration:**
    - Navigate to `Microservices/Common/config.py`.
    - Update the configuration with your specific MQTT broker details and Telegram API keys.

3.  **Launch the Ecosystem:**
    ```bash
    docker-compose up --build -d
    ```

---

## 🧑‍💻 Core Contributors

*   **Riccardo Fida** - [s327834@studenti.polito.it](mailto:s327834@studenti.polito.it)
*   **Hadi Ghavipeykar** - [s328181@studenti.polito.it](mailto:s328181@studenti.polito.it)

---
*Project Repository: [GitHub](https://github.com/HadiGhavi/Keeping-Elderly-People-at-Home-IOT-project)*

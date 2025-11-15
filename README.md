# 🚀 [Project Title]

> This project is a continuous health monitoring platform designed to close the gap between patients at home and their doctors. It solves the problem of "silent" critical events by using a Telegram bot to continuously monitor user-provided sensor data and instantly notifying both the patient and doctor when medical assistance may be required.

<p align="left">
  <img src="https://img.shields.io/github/license/YOUR_USERNAME/YOUR_REPO" alt="License">
  <img src="https://img.shields.io/github/workflow/status/YOUR_USERNAME/YOUR_REPO/build" alt="Build Status">
  <img src="https://img.shields.io/github/issues/YOUR_USERNAME/YOUR_REPO" alt="Issues">
</p>

![Project Screenshot/GIF]()

## ✨ Features

* Telegram Bot interaction
* Admin Dashboard for management
* Real-time Patient Monitoring
* Automated Critical Alerts
* Comprehensive Reporting
* Easy Deployment


## 📋 Table of Contents

* [Installation](#-installation)
* [Usage](#-usage)
* [Configuration](#-configuration)

---

## 🔧 Installation

**Prerequisites:**
* You must have **Git** installed.
* You must have **Docker** and **Docker Compose** installed.

**Steps:**
1.  Clone the repository:
    ```bash
    git clone https://github.com/HadiGhavi/Keeping-Elderly-People-at-Home-IOT-project.git
    ```
2.  Navigate to the project directory:
    ```bash
    cd YOUR_REPO
    ```

## 💡 Usage

1.  **Build and Start the Services:**
    Run the following commands in your terminal from the project's root directory.

    ```bash
    # (Optional) Stop any previous running instances
    docker-compose down
    
    # Build and start the application
    docker-compose up --build
    ```
    *You can add the `-d` flag (`docker-compose up --build -d`) to run the containers in the background (detached mode).*

2.  **Accessing the App:**
    Once the containers are running, you can use the application:
    * **Telegram Bot:** Interact with the bot directly on Telegram.
    * **Admin Dashboard:** Users with admin permissions can access the dashboard in their browser (at `http://localhost:9000`).

---

## ⚙️ Configuration

Before running `docker-compose up`, you must configure the application.

1.  Access the Microservices/Common folder 
2. Edit config.py with custom values


## 🧑‍💻 Contact

Riccardo Fida - s327834@studenti.polito.it

Project Link: https://github.com/HadiGhavi/Keeping-Elderly-People-at-Home-IOT-project
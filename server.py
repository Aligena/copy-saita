import socket
import threading
import datetime
import json
import os

# Пути к файлам с данными
CLAN_DATA_FILE = "clan_data.json"
USER_DATA_FILE = "user_data.json"
PLAYER_DATA_FILE = "player_data.json"
CHARACTER_DEFAULTS_FILE = "character_defaults.json"

# Размеры игрового поля
MAP_WIDTH = 50
MAP_HEIGHT = 50

# Загрузка данных о кланах
def load_clan_data():
    if os.path.exists(CLAN_DATA_FILE):
        with open(CLAN_DATA_FILE, "r") as file:
            content = file.read()
            if content:
                return json.loads(content)
    return {}

# Сохранение данных о кланах
def save_clan_data(data):
    with open(CLAN_DATA_FILE, "w") as file:
        json.dump(data, file, indent=4)

# Загрузка учетных данных
def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r") as file:
            content = file.read()
            if content:
                return json.loads(content)
    return {}

# Сохранение учетных данных
def save_user_data(data):
    with open(USER_DATA_FILE, "w") as file:
        json.dump(data, file, indent=4)

# Загрузка данных о персонажах
def load_player_data():
    if os.path.exists(PLAYER_DATA_FILE):
        with open(PLAYER_DATA_FILE, "r") as file:
            content = file.read()
            if content:
                return json.loads(content)
    return {}

# Сохранение данных о персонажах
def save_player_data(data):
    with open(PLAYER_DATA_FILE, "w") as file:
        json.dump(data, file, indent=4)

# Загрузка начальных параметров персонажа
def load_character_defaults():
    if os.path.exists(CHARACTER_DEFAULTS_FILE):
        with open(CHARACTER_DEFAULTS_FILE, "r") as file:
            content = file.read()
            if content:
                return json.loads(content)
    return {}

# Создание нового персонажа
def create_new_character(user_name):
    character_defaults = load_character_defaults()
    new_character = character_defaults.copy()
    new_character["user_name"] = user_name
    new_character["clan"] = None
    new_character["location"] = {"x": 0, "y": 0}  # Начальное местоположение
    return new_character

# Регистрация нового пользователя
def register_user(client_socket, user_data, player_data):
    client_socket.send("Введите имя пользователя: ".encode("utf-8"))
    user_name = client_socket.recv(1024).decode("utf-8").strip()

    if user_name in user_data:
        client_socket.send("Имя пользователя занято, попробуйте снова.".encode("utf-8"))
        return None, False
    else:
        client_socket.send("Введите пароль: ".encode("utf-8"))
        password = client_socket.recv(1024).decode("utf-8").strip()

        user_data[user_name] = password
        save_user_data(user_data)

        new_character = create_new_character(user_name)
        player_data[user_name] = new_character
        save_player_data(player_data)

        client_socket.send("Регистрация успешна!".encode("utf-8"))
        return user_name, True

# Обработка соединений
def handle_client(client_socket, client_address, user_data, player_data, clan_data, connections, online_users, pending_invitations):
    print(f"Новое соединение: {client_address}")

    client_socket.send("Введите команду: /register или /login.".encode("utf-8"))
    auth_success = False
    user_name = ""

    while not auth_success:
        try:
            data = client_socket.recv(1024).decode("utf-8").strip()

            if data == "/register":
                user_name, auth_success = register_user(client_socket, user_data, player_data)

            elif data == "/login":
                client_socket.send("Введите имя пользователя: ".encode("utf-8"))
                user_name = client_socket.recv(1024).decode("utf-8").strip()

                if user_name not in user_data:
                    client_socket.send("Имя пользователя не найдено.".encode("utf-8"))
                else:
                    client_socket.send("Введите пароль: ".encode("utf-8"))
                    password = client_socket.recv(1024).decode("utf-8").strip()

                    if password == user_data[user_name]:
                        client_socket.send("Авторизация успешна!".encode("utf-8"))
                        auth_success = True
                    else:
                        client_socket.send("Неверный пароль.".encode("utf-8"))

            else:
                client_socket.send("Неизвестная команда, введите /register или /login.".encode("utf-8"))

        except Exception as e:
            client_socket.send(f"Ошибка: {e}".encode("utf-8"))

    if auth_success:
        connections.append(client_socket)
        online_users.add(user_name)

        client_socket.send("Добро пожаловать! Узнать доступные команды /help.".encode("utf-8"))

        while True:
            try:
                data = client_socket.recv(1024).decode("utf-8").strip()

                if data.startswith("/"):
                    command = data[1:].strip().lower()
                    command_args = command.split(" ", 1)

                    # Команды перемещения
                    if command_args[0] == "move":
                        direction = command_args[1].lower()
                        current_location = player_data[user_name]["location"]

                        if direction == "north":
                            if current_location["y"] < MAP_HEIGHT - 1:
                                current_location["y"] += 1
                        elif direction == "south":
                            if current_location["y"] > -MAP_HEIGHT:  # Исправлено условие для юга
                                current_location["y"] -= 1
                        elif direction == "east":
                            if current_location["x"] < MAP_WIDTH - 1:
                                current_location["x"] += 1
                        elif direction == "west":
                            if current_location["x"] > -MAP_WIDTH:  # Исправлено условие для запада
                                current_location["x"] -= 1

                        save_player_data(player_data)

                        # После сохранения новых координат отправляем сообщение с новыми координатами
                        client_socket.send(f"Ваше новое местоположение: {current_location}".encode("utf-8"))


                    elif command_args[0] == "info":
                        if len(command_args) < 2:
                            client_socket.send("Укажите имя персонажа.".encode("utf-8"))
                        else:
                            info_name = command_args[1]

                            if info_name in player_data:
                                info = player_data[info_name]
                                response = f"Имя: {info_name}\nМестоположение: {info['location']}"
                                client_socket.send(response.encode("utf-8"))
                            else:
                                client_socket.send("Персонаж с таким именем не найден.".encode("utf-8"))

                    elif command_args[0] == "date":
                        current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        client_socket.send(f"Текущая дата: {current_date}".encode("utf-8"))

                    elif command_args[0] == "ip":
                        client_socket.send(f"Ваш IP-адрес: {client_address[0]}".encode("utf-8"))

                    elif command_args[0] == "online":
                        online_count = len(connections)
                        client_socket.send(f"Игроков онлайн: {online_count}".encode("utf-8"))

                    elif command_args[0] == "help":
                        help_message = (
                            "/date - текущая дата\n"
                            "/ip - ваш IP-адрес\n"
                            "/online - количество онлайн игроков\n"
                            "/clan [имя] - создать клан\n"
                            "/inviteclan [имя] - пригласить в клан\n"
                            "/cland [имя] - исключить из клана\n"
                            "/invites - список ваших предложений\n"
                            "/my - информация о вашем персонаже\n"
                            "/info [имя] - информация о персонаже по имени\n"
                            "/world [сообщение] - отправить сообщение в общий чат"
                        )
                        client_socket.send(f"Доступные команды:\n{help_message}".encode("utf-8"))

            except Exception as e:
                client_socket.send(f"Ошибка: {e}".encode("utf-8"))
                break

        connections.remove(client_socket)
        online_users.remove(user_name)
        client_socket.close()
        print(f"Соединение закрыто: {client_address}")

# Создание серверного сокета
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(("localhost", 12344))
server_socket.listen(5)

print("Сервер запущен")

# Обработка соединений в цикле
user_data = load_user_data()
player_data = load_player_data()
clan_data = load_clan_data()
connections = []
online_users = set()
pending_invitations = []

while True:
    client_socket, client_address = server_socket.accept()
    threading.Thread(target=handle_client, args=(client_socket, client_address, user_data, player_data, clan_data, connections, online_users, pending_invitations)).start()

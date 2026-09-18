"""Переменные окружения"""
import os

#print(os.environ)

with open(".env.test", mode="r", encoding="utf-8") as file:
    env = file.read()

env_name, env_value = env.split("=")

os.environ[env_name] = env_value

print(os.environ.get(env_name)) 
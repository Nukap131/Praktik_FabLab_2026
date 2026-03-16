# Tredje uge praktik i Fablab. 09 - 14.03.2026
I den 3 uge i Fablab har vi modtaget næsten alle komponenter/hardware, som skulle bruges.
Da jeg begyndte med at programmere i 2 uge, glemte jeg at AI-delen af kamera kunne bruges fra selve kamera og ikke belaste Raspberry Pi CPU, samt jeg lavede selv Flask webserver.
Jeg har gemt kodene som fablab_counter.py, men gik i gang med v2, hvor jeg skriver koden, så AI kører i kamera, ikke i CPU, så Pi bliver ikke hurtigt varmt.
Samtidig begyndte jeg at bruge MQTT og Grafana, så jeg ikke behøver at lave webserver selv.
Indtil videre har jeg SQLite database, MQTT, Grafana og automatiseret Raspberry Pi med systemd service.
I dag begydte jeg med 4 uge, og modtaget relæ. Fik snakket med Mads, som har udviklet tryk-knap systemet, som jeg skal automatisere med Raspberry.
Vi skal bruge relæ, så når person går ind og forbi kamera, sender Raspberry puls til relæ, så tryk-knap tælleren stiger automatisk. Det betyder, at denne uge vi skal fjerne tryk-knap systemet
og i gang med at teste den med Raspberry, samt sætte dem op, når vi er færdige.

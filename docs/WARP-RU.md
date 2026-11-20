# WARP в Amnezia Control

## Включение

1. Откройте «Настройки → WARP» и нажмите «Установить WARP». Требуются root, systemd, выход в интернет и свободное место. Панель загружает подписанный APT-пакет из официального репозитория Cloudflare; отдельно запущенный системный WARP не перезаписывается.
2. Прочитайте условия Cloudflare, поставьте флажок согласия и нажмите «Зарегистрировать WARP». Это регистрация устройства, а не DNS-домена. Перенос NS ждать не нужно. Учетная запись из браузера автоматически не используется. Это обычный потребительский WARP, не настройка организации Zero Trust или платной подписки.
3. Выберите протокол до Cloudflare: MASQUE или WireGuard. Выберите конкретные VPN-подключения либо все подключения, включая будущие. Все клиенты и дополнительные версии на выбранном подключении используют один маршрут.
4. Включите WARP и сохраните. Дождитесь статуса «Подключён». Проверяется HTTPS Cloudflare trace через интерфейс WARP, с проверкой сертификата и `warp=on/plus`.
5. Чтобы вернуть прямой выход, выключите WARP и сохраните. Открытые TCP-сессии могут потребовать переподключения, поскольку меняется внешний IP.

## Защита рабочих подключений

Официальный `warp-svc` работает в отдельном Linux network namespace `ac-warp`. Только IPv4-пакеты, пришедшие с выбранных VPN-интерфейсов, получают отдельный policy route. Основной маршрут VPS, локальные DNS, SSH и web-панель не переводятся в WARP. Транспорт WARP получает обычный NAT на сервере. DNS внутри namespace можно выбрать отдельно; пустое поле использует текущие upstream DNS VPS. Сам daemon использует `tunnel_only`, без изменения DNS системы.

При недоступном WARP выбранный трафик блокируется, включая попытку уйти через обычный транспорт namespace. Это намеренная защита от незаметной смены выхода. Отключение переключателя явно возвращает обычный выход. Проверка примерно каждые 20 секунд восстанавливает клиент после сбоя; блокировка действует до восстановления. После перезагрузки boot guard устанавливает правила раньше сетевых VPN-служб.

Существующие ключи, параметры обфускации и клиентские файлы при выборе WARP не пересоздаются. Старые и дополнительные версии одного клиента могут находиться на разных VPN-подключениях: выбирайте все нужные подключения.

## Совместимость и ограничения

- Поддерживаемые ОС установщика: Ubuntu 22.04/24.04/26.04 и Debian 12/13; amd64/arm64. Нужны официальные пакеты Cloudflare для выбранного релиза, сетевые namespaces и `/dev/net/tun`.
- В первой реализации маршрутизируется IPv4; IPv6 VPN-профили не поддерживаются. Пересылка IPv6 с выбранных VPN-интерфейсов блокируется, чтобы она не обошла WARP по обычному маршруту. Клиентский DNS также зависит от маршрутов в его конфиге: панель не исправляет DNS-утечки на устройствах автоматически.
- Извлекаются официальные headless-бинарники из пакета, без установки его GUI и без автоматического запуска общего `warp-svc`. Устанавливаются их системные зависимости. Это интеграция Amnezia Control с официальным клиентом, а не официальный установщик Cloudflare для namespace.
- Резервные ресурсы: namespace `ac-warp`, veth `acw-host/acw-ns`, подсеть `169.254.172.0/30`, policy table `51888`, priority `10888`. При занятости ресурсов первым включением операция останавливается.
- WARP не скрывает WireGuard/AmneziaWG на участке устройство → VPS и не гарантирует обход блокировок хостера/оператора. Домен, Cloudflare DNS proxy и сертификат web-панели не превращают UDP VPN в HTTPS.
- Сторонняя установленная служба WARP не принимается под управление автоматически.
- Регистрация и ключи Cloudflare содержат секреты. Они не выдаются API статуса и входят в резервную копию. Удаление панели сохраняет `/var/lib/cloudflare-warp` и общие APT-пакеты; сетевые ресурсы панели очищаются. Не публикуйте резервную копию.

## Диагностика

Статус задачи и понятная ошибка отображаются в панели. Подробности на VPS:

```sh
journalctl -u ac-warp-task -u ac-warp-client -u ac-warp-watch --no-pager -n 100
cat /var/lib/amnezia-control/warp/install.log
ip rule show
ip route show table 51888
```

Не публикуйте полный вывод клиента/Cloudflare account state без проверки на секреты. Для аварийного возврата прямого выхода:

```sh
sudo /opt/amnezia-control/.venv/bin/python /opt/amnezia-control/backend/warp.py disable
```

## Official sources / English

The WARP panel supports installation, explicit device registration and selected/all VPN IPv4 egress. MASQUE and WireGuard are supported. Host SSH, panel and DNS keep their original routing. Selected VPN traffic fails closed while WARP is unavailable. Disable and save to restore direct egress. DNS delegation is independent of device registration. Existing client keys and configuration files are preserved. This feature does not hide the client-to-VPS tunnel or unblock a filtered VPS IP. See the Russian sections above for implementation details and resource reservations.

- [Cloudflare Linux client](https://developers.cloudflare.com/warp-client/get-started/linux/)
- [WARP operating modes](https://developers.cloudflare.com/warp-client/warp-modes/)
- [Official signed APT repository](https://pkg.cloudflareclient.com/)
- [Cloudflare terms](https://www.cloudflare.com/application/terms/)

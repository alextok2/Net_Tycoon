import json

class IOSCommandProcessor:
    def __init__(self, session):
        self.session = session
        
        # !!! ДОБАВЬТЕ ЭТУ СТРОКУ !!!
        self.lab = session.lab
        
        self.device_name = getattr(session, 'current_device', 'Router') 
        
        # --- ИНИЦИАЛИЗАЦИЯ ---
        if self.device_name not in self.session.virtual_config:
            self.session.virtual_config[self.device_name] = {
                "config": {
                    "hostname": self.device_name,
                    "services": { # Новые глобальные настройки
                        "password-encryption": False,
                        "timestamps_log": True,   # По умолчанию в Cisco включено? (обычно да)
                        "timestamps_debug": True
                    },
                    "lines": { # Настройки линий
                        "con 0": {"login": False, "logging_sync": False},
                        "vty 0 4": {"login": False}, # В лабе сделаем дефолт no login для удобства
                        "vty 5 15": {"login": False}
                    }
                },
                "context": "privileged",
                "history": [],
                "console_logs": []
            }
            self.session.save()
            
        self.device_data = self.session.virtual_config[self.device_name]
        self.current_context = self.device_data.get("context", "privileged")


        # --- КАРТА ПРОМПТОВ (ДИНАМИЧЕСКАЯ) ---
        self.prompt_keys = {
            "privileged": "#",
            "global_config": "(config)#",
            "interface_config": "(config-if)#",
            "line_config": "(config-line)#",        # НОВОЕ
            "isakmp_config": "(config-isakmp)#",
        }

        # --- ДЕРЕВО СПРАВКИ (HELP TREE) ---
        # Формат: "контекст": [("команда", "описание"), ...]
        self.HELP_TREE = {
            # PRIVILEGED EXEC (Router#)
            "": [
                ("show", "Show running system information"),
                ("configure", "Enter configuration mode"),
                ("enable", "Turn on privileged commands"),
                ("exit", "Exit current mode"),
                ("copy", "Copy configuration files"),
                ("write", "Write running configuration to memory")
            ],
            "__global__": [
                ("hostname", "Set system's network name"),
                ("interface", "Select an interface to configure"),
                ("line", "Configure a terminal line"),          # НОВОЕ
                ("service", "Modify use of network based services"), # НОВОЕ
                ("crypto", "Encryption module"),
                ("access-list", "Add an access list entry"),
                ("exit", "Exit from configure mode"),
                ("no", "Negate a command or set its defaults"),
                ("do", "To run exec commands in config mode")
            ],
            "configure": [
                ("terminal", "Configure from the terminal"),
                ("<cr>", "")
            ],

            # !!! ДОБАВЛЕНО: Аргументы для команды interface !!!
            "interface": [
                ("FastEthernet0/0", ""),
                ("FastEthernet0/1", ""),
            ],
            
            # SERVICE
            "service": [
                ("password-encryption", "Encrypt system passwords"),
                ("timestamps", "Timestamp debug/log messages")
            ],
            "service timestamps": [("log", ""), ("debug", "")],

            # LINE CONFIG
            "line": [("console", "Primary terminal line"), ("vty", "Virtual terminal")],
            "__line__": [
                ("password", "Set a password"),
                ("login", "Enable password checking"),
                ("logging", "Modify message logging facilities"),
                ("no", "Negate a command"),
                ("exit", "Exit from line configuration mode")
            ],
            "logging": [("synchronous", "Synchronized message output")],

            # INTERFACE CONFIG
            "__interface__": [
                ("ip", "Interface Internet Protocol config commands"),
                ("description", "Interface specific description"),
                ("shutdown", "Shutdown the selected interface"),
                ("no", "Negate a command or set its defaults"),
                ("exit", "Exit from interface configuration mode")
            ],
            
            # ... (Остальные команды show, crypto и т.д. остаются как были) ...
            "show": [
                ("running-config", "Current operating configuration"),
                ("ip", "IP information"),
                ("interface", "Interface status and configuration"),
                
                ("crypto", "Encryption module")
            ],
             "show interface": [
                ("FastEthernet0/0", ""),
                ("FastEthernet0/1", ""),
                ("description", "Show descriptions"),
                ("<cr>", "Output modifiers")
                
            ],
            # Добавим hostname для автодополнения, если кто-то введет "hostname ?"
            "hostname": [
                ("<WORD>", "This system's network name")
            ]
        }


        # Добавляем контексты для ISAKMP (Phase 1)
        self.HELP_TREE_ISAKMP = {
            "": [
                ("encryption", "Set encryption algorithm"),
                ("authentication", "Set authentication method"),
                ("group", "Set Diffie-Hellman group"),
                ("exit", "Exit to global config")
            ],
            "encryption": [("aes", ""), ("3des", ""), ("des", "")],
            "authentication": [("pre-share", "")],
            "group": [("1", ""), ("2", ""), ("5", "")]
        }

    # --- 1. НОРМАЛИЗАЦИЯ ---
    def normalize_command(self, raw_command):
        """
        Динамически разворачивает сокращения, используя HELP_TREE.
        Пример: 'sh int d' -> 'show interface description'
        """
        tokens = raw_command.strip().lower().split()
        if not tokens: return ""

        # 1. Определяем стартовый контекст дерева
        if self.current_context == "global_config": current_key = "__global__"
        elif self.current_context == "interface_config": current_key = "__interface__"
        elif self.current_context == "line_config": current_key = "__line__"
        else: current_key = "" # Privileged
        
        expanded_tokens = []
        
        # Флаг, что мы перестали понимать команды и пошли аргументы (IP адреса, имена)
        # Как только мы не нашли совпадение в дереве, дальше не расширяем.
        parsing_args = False

        for token in tokens:
            if parsing_args:
                expanded_tokens.append(token)
                continue

            # Получаем доступные команды на этом уровне
            options = self.HELP_TREE.get(current_key, [])
            
            # Ищем совпадения по префиксу
            matches = []
            for item in options:
                # Защита от плохих данных
                if not isinstance(item, (list, tuple)) or len(item) < 1: continue
                cmd_name = item[0]
                
                # Пропускаем плейсхолдеры типа <cr> или <WORD>
                if cmd_name.startswith("<"): continue
                
                if cmd_name.startswith(token):
                    matches.append(cmd_name)
            
            # ЛОГИКА ВЫБОРА
            if len(matches) == 1:
                # УРА! Нашли уникальное совпадение (например "sh" -> "show")
                full_word = matches[0]
                expanded_tokens.append(full_word)
                
                # Сдвигаем контекст для следующего слова
                # Если мы в корне (специальные ключи), то новый ключ просто слово ("show")
                # Если уже внутри, добавляем через пробел ("show" -> "show interface")
                if current_key.startswith("__") or current_key == "":
                    current_key = full_word
                else:
                    current_key += " " + full_word
            
            elif len(matches) > 1:
                # АМБИГУАЦИЯ (неоднозначность)
                # Например "co" может быть "configure" или "copy"
                # Если есть точное совпадение введенного слова с одним из вариантов - берем его
                if token in matches:
                    expanded_tokens.append(token)
                    if current_key.startswith("__") or current_key == "": current_key = token
                    else: current_key += " " + token
                else:
                    # Если точного нет, оставляем как есть (пусть handler ругается "ambiguous")
                    expanded_tokens.append(token)
                    parsing_args = True # Дальше дерево не строим
            
            else:
                # НЕТ СОВПАДЕНИЙ
                # Это аргумент (имя хоста, IP, интерфейс Fa0/0)
                expanded_tokens.append(token)
                parsing_args = True # Переходим в режим аргументов

        return " ".join(expanded_tokens)


    def _expand_interface_name(self, short_name):
        """
        Превращает f0/0, fa0/0, fast0/0 в FastEthernet0/0.
        Если не распознано, возвращает оригинал.
        """
        s = short_name.lower()
        # FastEthernet
        if s.startswith("f") and "ethernet" not in s:
             # Берем цифры из конца
             # fa0/0 -> 0/0
             # f0/1 -> 0/1
             # fast0/0 -> 0/0
             parts = s.replace("fast", "").replace("fa", "").replace("f", "")
             return "FastEthernet" + parts
        
        # GigabitEthernet (на будущее)
        if s.startswith("g") and "ethernet" not in s:
             parts = s.replace("gig", "").replace("gi", "").replace("g", "")
             return "GigabitEthernet" + parts
             
        return short_name

    # --- 2. ГЛАВНЫЙ ПРОЦЕССОР ---
    def process_input(self, raw_command):
        prompt_before = self._get_current_prompt()

        if raw_command.rstrip().endswith("?"):
            return self._handle_context_help(raw_command)

        command = self.normalize_command(raw_command)
        response_text = ""

        if not command:
            pass
        elif command in ["exit", "end"]:
            self._handle_exit(command)
            self._save_state()
        else:
            try:
                if self.current_context == "privileged":
                    response_text = self._handle_privileged(command)
                elif self.current_context == "global_config":
                    response_text = self._handle_global_config(command)
                elif self.current_context == "interface_config":
                    response_text = self._handle_interface_config(command)
                elif self.current_context == "line_config":    # НОВОЕ
                    response_text = self._handle_line_config(command)
                elif self.current_context == "isakmp_config":
                    response_text = self._handle_isakmp_config(command)
                else:
                    response_text = "% Error: Unknown mode implementation"
            except Exception as e:
                response_text = f"% System Error: {str(e)}"

        self.device_data.setdefault("console_logs", []).append({
            "type": "cmd", "text": raw_command, "prompt": prompt_before
        })
        if response_text:
            self.device_data["console_logs"].append({
                "type": "out", "text": response_text
            })
        if raw_command.strip():
            self.device_data["history"].append(raw_command)

        self._save_state()
        return self._get_response(response_text)



    def _save_state(self):
        self.device_data["context"] = self.current_context
        self.session.virtual_config[self.device_name] = self.device_data
        self.session.save()

    def _get_current_prompt(self):
        cfg = self.device_data["config"]
        hostname = cfg.get("hostname", self.device_name)
        suffix = self.prompt_keys.get(self.current_context, "#")
        return f"{hostname}{suffix}"


    def _get_response(self, text_output):
        cfg = self.device_data["config"]
        current_hostname = cfg.get("hostname", self.device_name)
        
        # !!! ИСПРАВЛЕНИЕ: Запускаем проверку задания при каждом ответе !!!
        is_done = self.check_completion()
        
        return {
            "output": text_output,
            "prompt": self._get_current_prompt(),
            "is_completed": is_done, # Теперь передаем реальный результат
            "hostname": current_hostname
        }




    # --- 3. ОБРАБОТЧИКИ СПРАВКИ ---
    def _handle_context_help(self, raw_command):
        clean_input = raw_command.replace('?', '').rstrip()
        space_before = raw_command.replace('?', '').endswith(' ')
        
        # Нормализуем всю строку сразу, чтобы "show int" стало "show interface"
        # Это решает проблему поиска ключа
        normalized_full = self.normalize_command(clean_input)
        tokens = normalized_full.split()

        context_key = ""
        prefix = ""

        if not tokens and not space_before:
            # Корень (просто "?")
            if self.current_context == "global_config": context_key = "__global__"
            elif self.current_context == "interface_config": context_key = "__interface__"
            elif self.current_context == "line_config": context_key = "__line__"
            else: context_key = ""
        
        elif space_before:
            # Закончили слово ("show int ?") -> ищем опции для "show interface"
            context_key = normalized_full
            prefix = ""
            
        else:
            # Не закончили слово ("show in?") -> ищем опции для "show", начинающиеся на "in"
            if len(tokens) == 1:
                 # Первое слово
                 if self.current_context == "global_config": context_key = "__global__"
                 elif self.current_context == "interface_config": context_key = "__interface__"
                 else: context_key = ""
                 prefix = tokens[0]
            else:
                 # "show interface fa" -> Context="show interface", Prefix="fa"
                 context_key = " ".join(tokens[:-1])
                 prefix = tokens[-1]

        # Ищем в дереве
        options = self.HELP_TREE.get(context_key, [])
        
        # Если опций нет, возможно мы ввели что-то, чего нет в словаре как ключа
        if not options and context_key:
             # Попробуем найти частичное совпадение ключа? Нет, это сложно.
             # Просто вернем ошибку или пустоту
             pass

        matches = []
        prefix_lower = prefix.lower()
        
        for item in options:
            if not isinstance(item, (list, tuple)) or len(item) < 2: continue
            name = item[0]
            desc = item[1]
            if name.lower().startswith(prefix_lower):
                matches.append((name, desc))
        
        if not matches: return self._get_response("% Unrecognized command")
        
        out = [f"  {n:<20} {d}" for n, d in matches]
        return self._get_response("\n".join(out))




    # --- 4. ЛОГИКА КОМАНД (HANDLERS) ---

    def _handle_line_config(self, cmd):
        """Обработка команд внутри line con 0 / line vty"""
        config = self.device_data["config"]
        line_name = self.device_data.get("current_line")
        
        if not line_name or line_name not in config.get("lines", {}):
             self.current_context = "global_config"
             return "% Error: Line context lost."

        line_cfg = config["lines"][line_name]

        if cmd.startswith("password"):
            # password cisco
            line_cfg["password"] = cmd.split()[-1]
            return ""
        
        if cmd == "login":
            line_cfg["login"] = True
            return ""
            
        if cmd == "no login":
            line_cfg["login"] = False
            return ""
            
        if "logging synchronous" in cmd:
            line_cfg["logging_sync"] = not cmd.startswith("no ")
            return ""

        return "% Invalid input detected."


    def _handle_exit(self, cmd):
        if cmd == "end":
            self.current_context = "privileged"
            return
        # Цепочка выхода: iface/line -> global -> priv
        if self.current_context == "global_config":
            self.current_context = "privileged"
        elif self.current_context != "privileged":
            self.current_context = "global_config"


    def _handle_privileged(self, cmd):
        if cmd == "configure terminal":
            self.current_context = "global_config"
            return "Enter configuration commands, one per line.  End with CNTL/Z."
        elif cmd.startswith("show"):
            return self._simulate_show_commands(cmd)
        elif cmd == "write" or cmd == "copy running-config startup-config":
            return "Building configuration...\n[OK]"
        return "% Invalid input detected."


    def _handle_global_config(self, cmd):
        real_cmd = cmd[3:] if cmd.startswith("do ") else cmd
        if real_cmd.startswith("show"): return self._simulate_show_commands(real_cmd)

        config = self.device_data["config"]
        
        # --- SERVICES (service password-encryption) ---
        if cmd.startswith("service ") or cmd.startswith("no service "):
            is_no = cmd.startswith("no ")
            clean = cmd[3:] if is_no else cmd
            
            if "services" not in config: config["services"] = {}
            services = config["services"]
            
            if "password-encryption" in clean:
                services["password-encryption"] = not is_no
                return ""
            if "timestamps" in clean:
                if "log" in clean: services["timestamps_log"] = not is_no
                if "debug" in clean: services["timestamps_debug"] = not is_no
                return ""

        # --- HOSTNAME ---
        if cmd.startswith("hostname"):
            parts = cmd.split()
            if len(parts) > 1: config["hostname"] = parts[1]
            return ""

        # --- LINE CONFIG ---
        if cmd.startswith("line "):
            # line console 0 / line vty 0 4
            parts = cmd.split()
            line_name = "unknown"
            
            if "console" in cmd and "0" in cmd: line_name = "con 0"
            elif "vty" in cmd:
                # Упрощение: если vty 0 -> vty 0 4
                if "0" in parts and "4" in parts: line_name = "vty 0 4"
                elif "5" in parts and "15" in parts: line_name = "vty 5 15"
                elif "0" in parts: line_name = "vty 0 4" # Fallback
            
            if line_name == "unknown": return "% Invalid line"

            self.current_context = "line_config"
            self.device_data["current_line"] = line_name
            
            # Инит конфига линий
            if "lines" not in config: config["lines"] = {}
            if line_name not in config["lines"]: config["lines"][line_name] = {}
            return ""

        # --- INTERFACE ---
        # INTERFACE (Улучшенное распознавание)
        if cmd.startswith("interface"):
            parts = cmd.split()
            if len(parts) < 2: return "% Incomplete command."
            
            # Используем утилиту
            target_iface = self._expand_interface_name(parts[1])

            # Проверка на валидность (только Fa0/0 и Fa0/1 разрешены в лабе)
            # Но если мы хотим разрешить создание Loopback, можно смягчить
            valid_ports = ["FastEthernet0/0", "FastEthernet0/1"]
            
            # Для надежности приведем к правильному регистру из списка valid_ports
            final_name = target_iface # Fallback
            for vp in valid_ports:
                if vp.lower() == target_iface.lower():
                    final_name = vp
                    break
            
            self.current_context = "interface_config"
            if "interfaces" not in config: config["interfaces"] = {}
            if final_name not in config["interfaces"]: config["interfaces"][final_name] = {}
            self.device_data["current_iface"] = final_name
            return ""

        # --- CRYPTO / ACL ---
        if cmd.startswith("crypto isakmp policy"):
            self.current_context = "isakmp_config"
            policy_id = cmd.split()[-1]
            if "isakmp_policies" not in config: config["isakmp_policies"] = {}
            if policy_id not in config["isakmp_policies"]: config["isakmp_policies"][policy_id] = {}
            self.device_data["editing_policy_id"] = policy_id
            return ""
        
        if cmd.startswith("access-list"):
            if "acls" not in config: config["acls"] = []
            config["acls"].append(cmd)
            return ""

        return "% Invalid input detected."


    def _handle_interface_config(self, cmd):
        # --- НОВОЕ: Разрешаем переключение интерфейса без exit ---
        if cmd.startswith("interface"):
             # Вызываем обработчик глобального режима, он умеет переключать интерфейсы
             return self._handle_global_config(cmd)
        # ---------------------------------------------------------

        config = self.device_data["config"]

        
        # 1. Достаем имя интерфейса из сохраненного состояния
        current_iface_name = self.device_data.get("current_iface")
        
        # Защита от сбоев (если вдруг контекст есть, а имени нет)
        if not current_iface_name or "interfaces" not in config:
            self.current_context = "global_config"
            return "% Error: Interface context lost. Returning to global config."

        # Получаем ссылку на словарь конфига конкретного интерфейса
        iface_config = config["interfaces"].get(current_iface_name)
        
        # Если интерфейс был удален пока мы в нем сидели (редкий кейс)
        if iface_config is None:
             return "% Error: Interface no longer exists."

        # --- КОМАНДЫ ИНТЕРФЕЙСА ---
        
        # 2. DESCRIPTION
        if cmd.startswith("description"):
            # Отрезаем "description " (12 символов)
            desc_text = cmd[12:].strip()
            iface_config["description"] = desc_text
            return ""

        # 3. IP ADDRESS
        if cmd.startswith("ip address"):
            parts = cmd.split()
            # Ожидаем: ip address 1.1.1.1 255.255.255.0
            if len(parts) >= 4:
                iface_config["ip_address"] = parts[2]
                iface_config["mask"] = parts[3]
            elif len(parts) == 2 and parts[1] == "dhcp":
                 iface_config["ip_address"] = "dhcp"
            else:
                return "% Incomplete command."
            return ""
            
        # 4. NO SHUTDOWN
        if cmd == "no shutdown":
            iface_config["status"] = "up"
            # Автоматически меняем line protocol (упрощение)
            iface_config["protocol"] = "up"
            return "% Link changed, interface is up"
            
        # 5. SHUTDOWN
        if cmd == "shutdown":
            iface_config["status"] = "administratively down"
            iface_config["protocol"] = "down"
            return "% Link changed, interface is administratively down"

        return "% Invalid input detected."




    def _handle_isakmp_config(self, cmd):
        # Контекст настройки политики (Phase 1)
        config = self.device_data["config"]
        policy_id = self.device_data.get("editing_policy_id")
        
        if not policy_id: return "% Error: No policy selected"
        
        policy = config["isakmp_policies"][policy_id]
        
        if cmd.startswith("encryption"): policy["encryption"] = cmd.split()[-1]
        elif cmd.startswith("authentication"): policy["authentication"] = cmd.split()[-1]
        elif cmd.startswith("group"): policy["group"] = cmd.split()[-1]
        
        return ""

    # --- 5. SHOW COMMANDS SIMULATION ---
    def _simulate_show_commands(self, cmd):
        # Нормализованная команда
        # cmd может быть "show running-config" или "show interface fa0/1"
        
        # 1. show running-config
        if "run" in cmd:
            return self._generate_running_config()
        
        parts = cmd.split()
        
        # 2. show ip interface brief
        # Логика: наличие 'ip' и ('int' или 'interface')
        if "ip" in parts and ("interface" in parts or "int" in cmd):
            interfaces = self.device_data["config"].get("interfaces", {})
            
            header = f"{'Interface':<20} {'IP-Address':<15} {'OK?':<4} {'Status':<20} {'Protocol':<10}"
            lines = [header]
            
            # Стандартные интерфейсы + созданные пользователем
            std_ifaces = ["FastEthernet0/0", "FastEthernet0/1"]
            all_ifaces = sorted(list(set(std_ifaces) | set(interfaces.keys())))

            for iface in all_ifaces:
                cfg = interfaces.get(iface, {})
                ip = cfg.get("ip_address", "unassigned")
                status = cfg.get("status", "administratively down")
                # Упрощенно: если порт UP, протокол тоже UP
                proto = "up" if status == "up" else "down"
                lines.append(f"{iface:<20} {ip:<15} {'YES':<4} {status:<20} {proto:<10}")
                
            return "\n".join(lines)

        # 3. show interface ...
        if "interface" in cmd or "interfaces" in cmd: # Поддержка множественного числа
            
            # Если аргументов нет ("show interface"), показываем все
            if len(parts) == 2:
                hardware_interfaces = ["FastEthernet0/0", "FastEthernet0/1"]
                outputs = [self._generate_interface_detail(hw) for hw in hardware_interfaces]
                return "\n".join(outputs)
            
            # Если есть аргумент ("show interface fa0/0" или "show int desc")
            if len(parts) > 2:
                raw_arg = parts[2] # Третье слово
                
                # А) Проверка на show interface description
                if "description".startswith(raw_arg.lower()):
                    interfaces = self.device_data["config"].get("interfaces", {})
                    header = f"{'Interface':<25} {'Status':<12} {'Protocol':<10} {'Description'}"
                    lines = [header]
                    
                    std_ifaces = ["FastEthernet0/0", "FastEthernet0/1"]
                    all_ifaces = sorted(list(set(std_ifaces) | set(interfaces.keys())))

                    for iface in all_ifaces:
                        cfg = interfaces.get(iface, {})
                        status = cfg.get("status", "admin down")
                        status_str = "up" if status == "up" else "admin down"
                        proto = "up" if status == "up" else "down"
                        desc = cfg.get("description", "")
                        lines.append(f"{iface:<25} {status_str:<12} {proto:<10} {desc}")
                        
                    return "\n".join(lines)

                # Б) Проверка на конкретный интерфейс
                # Разворачиваем имя (fa0/1 -> FastEthernet0/1)
                full_name = self._expand_interface_name(raw_arg)
                
                # Ищем точное совпадение среди доступных (case-insensitive)
                hardware_interfaces = ["FastEthernet0/0", "FastEthernet0/1"]
                
                for hw in hardware_interfaces:
                    if hw.lower() == full_name.lower():
                        return self._generate_interface_detail(hw)
                
                return "% Invalid interface type and number"

        return "% Invalid input detected at '^' marker."
    
    def _generate_interface_detail(self, iface_name):
        """Генерирует детальный вывод для show interface"""
        
        # Получаем конфиг из БД
        interfaces_cfg = self.device_data["config"].get("interfaces", {})
        specific_cfg = interfaces_cfg.get(iface_name, {})
        
        # Определяем статус
        # По умолчанию в Cisco интерфейсы административно выключены, 
        # но для удобства лабы Fa0/0 сделаем UP, а Fa0/1 DOWN, если не настроено иное
        default_status = "up" if iface_name == "FastEthernet0/0" else "administratively down"
        status = specific_cfg.get("status", default_status)
        
        # Line protocol обычно падает, если порт down
        proto = "down" if "down" in status else "up"
        
        # MAC адрес (фейковый, но разный)
        mac_suffix = "01" if "0/0" in iface_name else "02"
        mac = f"0000.0000.00{mac_suffix}"
        
        # IP адрес
        ip_info = ""
        if "ip_address" in specific_cfg:
            ip = specific_cfg["ip_address"]
            mask = specific_cfg.get("mask", "255.255.255.0")
            ip_info = f"\n  Internet address is {ip}/{mask}" # В реальности маска конвертируется в CIDR, но оставим так
        
        # Description
        desc_str = ""
        if "description" in specific_cfg:
            desc_str = f"\n  Description: {specific_cfg['description']}"

        return (
            f"{iface_name} is {status}, line protocol is {proto} {desc_str}\n"
            f"  Hardware is AmdFE, address is {mac} (bia {mac}){ip_info}\n"
            f"  MTU 1500 bytes, BW 100000 Kbit, DLY 100 usec,\n"
            f"     reliability 255/255, txload 1/255, rxload 1/255\n"
            f"  Encapsulation ARPA, loopback not set\n"
            f"  Keepalive set (10 sec)\n"
            f"  Full-duplex, 100Mb/s, 100BaseTX/FX"
        )
    def _generate_running_config(self):
        """Генерирует ПОЛНЫЙ конфиг на основе состояния"""
        c = self.device_data["config"]
        svcs = c.get("services", {})
        lines = []

        lines.append(f"Building configuration...\n")
        lines.append(f"Current configuration : 1024 bytes")
        lines.append("!")
        lines.append("version 15.1")
        
        # SERVICES
        # По умолчанию timestamps включены. Если False -> пишем no service ...
        if not svcs.get("timestamps_log", True): lines.append("no service timestamps log datetime msec")
        else: lines.append("service timestamps log datetime msec")
        
        if not svcs.get("timestamps_debug", True): lines.append("no service timestamps debug datetime msec")
        else: lines.append("service timestamps debug datetime msec")
        
        # По умолчанию encryption выключено. Если True -> пишем service ...
        if svcs.get("password-encryption", False): lines.append("service password-encryption")
        else: lines.append("no service password-encryption")
        
        lines.append("!")
        lines.append(f"hostname {c.get('hostname', self.device_name)}")
        lines.append("!")
        lines.append("boot-start-marker")
        lines.append("boot-end-marker")
        lines.append("!")
        
        # INTERFACES
        interfaces = c.get("interfaces", {})
        std_ifaces = ["FastEthernet0/0", "FastEthernet0/1"]
        all_ifaces = sorted(list(set(std_ifaces) | set(interfaces.keys())))

        for iface in all_ifaces:
            if_data = interfaces.get(iface, {})
            lines.append(f"interface {iface}")
            if "description" in if_data: lines.append(f" description {if_data['description']}")
            if "ip_address" in if_data:
                lines.append(f" ip address {if_data['ip_address']} {if_data.get('mask', '255.255.255.0')}")
            else: lines.append(" no ip address")
            
            lines.append(" duplex auto")
            lines.append(" speed auto")
            
            if if_data.get("status") != "up": lines.append(" shutdown")
            lines.append("!")

        # LINES
        lines_cfg = c.get("lines", {})
        
        # Console 0
        lines.append("line con 0")
        con = lines_cfg.get("con 0", {})
        if con.get("logging_sync"): lines.append(" logging synchronous")
        if not con.get("login"): lines.append(" no login")
        else: lines.append(" login")
        if "password" in con: lines.append(f" password {con['password']}")

        # VTY 0 4
        lines.append("line vty 0 4")
        vty = lines_cfg.get("vty 0 4", {})
        if vty.get("login"): lines.append(" login")
        else: lines.append(" no login") # В лабе по дефолту no login для удобства
        if "password" in vty: lines.append(f" password {vty['password']}")
        
        # VTY 5 15
        lines.append("line vty 5 15")
        vty5 = lines_cfg.get("vty 5 15", {})
        if vty5.get("login"): lines.append(" login")
        else: lines.append(" no login")
        
        lines.append("!")
        lines.append("end")
        
        return "\n".join(lines)

    def check_completion(self):
        criteria = self.lab.success_criteria
        if not criteria: return False

        user_data = self.session.virtual_config

        for dev_id, requirements in criteria.items():
            dev_config = user_data.get(dev_id, {}).get("config", {})
            
            # 1. Hostname (Сравниваем без учета регистра)
            req_hostname = requirements.get("hostname")
            if req_hostname:
                curr_hostname = dev_config.get("hostname", "")
                if curr_hostname.lower() != req_hostname.lower():
                    print(f"[CHECK FAIL] {dev_id} Hostname: Got '{curr_hostname}', Expected '{req_hostname}'")
                    return False

            # 2. Config Checks
            checks = requirements.get("config_checks", [])
            for check in checks:
                path = check.get("path", [])
                expected_value = str(check.get("value", "")).strip()
                
                # Ищем значение в конфиге юзера
                current_val = dev_config
                try:
                    for key in path:
                        # Если ключ - интерфейс, пробуем нормализовать (Fa0/0 -> FastEthernet0/0)
                        # Но у нас в конфиге ключи уже полные, так что просто берем
                        current_val = current_val.get(key)
                        if current_val is None: break
                except AttributeError:
                    current_val = None
                
                val_str = str(current_val).strip() if current_val else ""
                
                # СРАВНЕНИЕ (IGNORE CASE)
                if val_str.lower() != expected_value.lower():
                    print(f"[CHECK FAIL] {dev_id} Path {path}: Got '{val_str}', Expected '{expected_value}'")
                    return False

        # Если дошли сюда - всё верно
        print(f"[CHECK SUCCESS] Lab completed by user {self.session.user}")
        self.session.is_completed = True
        self.session.save()
        return True


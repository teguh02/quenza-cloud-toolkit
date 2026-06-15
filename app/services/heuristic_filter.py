class HeuristicPreFilter:
    """
    A dedicated class for heuristic scanning of script files.
    Maintains vocabularies of suspicious keywords categorized by language
    or general OS commands, based on OWASP and NIST guidelines for detecting
    webshells and backdoors.
    """
    
    def __init__(self):
        # PHP specific high-risk keywords
        # Sources: OWASP Webshell Detection, NIST SP 800-184, known PHP webshell signatures
        self.php_keywords = [
            # Code execution & eval-based obfuscation
            "eval(", "assert(", "preg_replace('/./e'", "create_function(",
            "call_user_func(", "call_user_func_array(", "array_map('assert'",
            "array_filter(", "usort(", "uasort(", "uksort(",

            # Obfuscation & encoding functions
            "base64_decode", "base64_encode", "gzinflate(", "gzdeflate(",
            "gzdecode(", "gzuncompress(", "gzcompress(", "str_rot13(",
            "hex2bin(", "hexdec(", "convert_uufrombase64", "rawurldecode(",
            "str_replace(", "strrev(", "chunk_split(", "pack(",

            # Shell execution
            "exec(", "system(", "shell_exec(", "passthru(", "proc_open(",
            "pcntl_exec(", "popen(", "proc_get_status(", "proc_terminate(",

            # Superglobals / Input sources
            "$_POST", "$_GET", "$_REQUEST", "$_COOKIE", "$_FILES",
            "$_SERVER['http_", "$_server[", "$http_raw_post_data",
            "getallheaders(", "apache_request_headers(",

            # File operations (upload, write, overwrite)
            "file_put_contents(", "move_uploaded_file(", "copy(", "rename(",
            "file_get_contents(", "fopen(", "fwrite(", "fputs(", "unlink(",
            "glob(", "opendir(", "readdir(", "scandir(", "symlink(",

            # Network & socket
            "fsockopen(", "pfsockopen(", "stream_socket_client(",
            "curl_exec(", "curl_setopt(", "file(", "fgets(",
            "stream_get_contents(", "get_headers(", "http_get(",

            # Dynamic code / reflection tricks
            "${'_'.$_}", "$$", "${$", "chr(", "ord(",
            "implode(array_map(chr", "join(array_map(chr",
            "serialize(", "unserialize(", "object_vars(",
            "class_exists(", "function_exists(", "method_exists(",
            "preg_replace(", "register_shutdown_function(",
            "register_tick_function(", "set_error_handler(",

            # Backdoor / c99 / r57 indicators
            "c99shell", "r57shell", "wso shell", "b374k",
            "phpspy", "indoxploit", "p0wny", "weevely",
            "FilesMan", "passthru", "bypass_", "@eval",

            # Misc dangerous
            "ini_set('allow_url", "ini_set('disable_functions",
            "ini_restore(", "putenv(", "apache_setenv(",
            "dl(", "php_uname(", "phpinfo(", "posix_getpwuid(",
            "posix_kill(", "posix_setuid(",
        ]
        
        # JavaScript / Node.js specific
        # Sources: OWASP Top 10, Node.js security best practices, known JS backdoor patterns
        self.js_keywords = [
            # Node.js child process execution
            "child_process.exec(", "child_process.execsync(",
            "child_process.spawn(", "child_process.spawnsync(",
            "child_process.execfile(", "child_process.fork(",
            "require('child_process')", 'require("child_process")',
            "spawnSync(", "execFileSync(", "execSync(",

            # Dynamic code execution
            "eval(", "new function(", "settimeout(", "setinterval(",
            "setimmediate(", "function()(", "function(){eval",
            "vm.runincontext(", "vm.runinnewcontext(",
            "vm.script(", "vm.module(",

            # Obfuscation patterns
            "\\x65\\x76\\x61\\x6c", "\\u0065\\u0076\\u0061\\u006c",
            "string.fromcharcode(", "atob(", "btoa(",
            "unescape(", "decodeuri(", "decodeuricomponent(",
            "fromcharcode(", "charcodeat(",

            # File system access
            "fs.writefile(", "fs.writefilesync(", "fs.appendfile(",
            "fs.unlink(", "fs.rmsync(", "fs.mkdirsync(",
            "fs.readfilesync(", "fs.creadestream(", "fs.writesync(",

            # Network / HTTP calls
            "http.request(", "https.request(", "net.connect(",
            "net.createsocket(", "dgram.createsocket(",
            "xmlhttprequest(", "fetch(",

            # Process manipulation
            "process.env", "process.exit(", "process.binding(",
            "process.mainmodule", "__dirname", "__filename",

            # Prototype pollution
            "__proto__", "constructor.prototype", "object.assign(",
            "object.defineproperty(",

            # Known JS webshell/backdoor patterns
            "shell_exec", "b64decode", "hexdecode",
            "os.system", "reverse shell",
        ]
        
        # Python specific
        # Sources: NIST, known Python reverse shells, common pentest payloads
        self.python_keywords = [
            # OS command execution
            "os.system(", "os.popen(", "os.execv(", "os.execve(",
            "os.execvp(", "os.spawnl(", "os.fork(", "os.kill(",
            "os.getenv(", "os.putenv(",

            # Subprocess execution
            "subprocess.call(", "subprocess.popen(", "subprocess.run(",
            "subprocess.check_output(", "subprocess.check_call(",
            "subprocess.getoutput(", "subprocess.getstatusoutput(",

            # Dynamic code execution
            "eval(", "exec(", "compile(", "execfile(",
            "__import__(", "importlib.import_module(",

            # Network / socket reverse shells
            "socket.socket(", "socket.af_inet", "socket.sock_stream",
            "s.connect(", "s.bind(", "s.listen(", "s.accept(",
            "pty.spawn(", "pty.openpty(",

            # Obfuscation tricks
            "__import__('os')", '__import__("os")',
            "getattr(__builtins__", "getattr(os,", "vars()['",
            "globals()['", "locals()['", "dir()",
            "chr(", "ord(", "b64decode(", "codecs.decode(",
            "zlib.decompress(", "marshal.loads(",
            "base64.b64decode(", "base64.decodebytes(",
            "pickle.loads(", "pickle.load(", "unpickle(",

            # File operations
            "open(", "shutil.copy(", "shutil.move(", "shutil.rmtree(",
            "os.remove(", "os.unlink(", "os.mkdir(", "os.makedirs(",

            # Known reverse shell payloads
            "pty.spawn('/bin/bash')", "pty.spawn('/bin/sh')",
            "bash -i >& /dev/tcp", "/dev/tcp/",
            "os.dup2(s.fileno()", "os.dup2(sock.fileno(",

            # Misc dangerous builtins / reflection
            "__builtins__", "__class__", "__mro__",
            "__subclasses__", "type.__subclasses__",
            "ctypes.cdll", "ctypes.windll",
        ]
        
        # General OS commands / Shells (language-agnostic, checked for ALL file types)
        # Sources: MITRE ATT&CK T1059, common reverse shell cheatsheets
        self.os_keywords = [
            # Windows shells
            "cmd.exe", "powershell", "powershell.exe", "wscript.exe",
            "cscript.exe", "mshta.exe", "rundll32.exe", "regsvr32.exe",
            "certutil.exe", "bitsadmin.exe", "wmic.exe",

            # Unix/Linux shells
            "/bin/sh", "/bin/bash", "/bin/zsh", "/bin/ksh",
            "/usr/bin/python", "/usr/bin/perl", "/usr/bin/ruby",
            "bash -i", "bash -c", "sh -c", "sh -i",

            # Netcat / reverse shell patterns
            "nc -e", "nc -lvp", "nc -nv", "ncat -e",
            "ncat --exec", "/dev/tcp/", "/dev/udp/",

            # Common pentest / post-exploitation tools
            "msfvenom", "metasploit", "meterpreter",
            "cobalt strike", "cobaltstrike", "beacon.exe",
            "mimikatz", "lazagne", "bloodhound",
            "empire", "powersploit",

            # Download cradles
            "wget http", "curl http", "curl -o", "curl -s http",
            "invoke-webrequest", "invoke-expression",
            "iex(", "iex (new-object",
            "(new-object net.webclient).downloadstring",
            "(new-object net.webclient).downloadfile",

            # Privilege escalation hints
            "chmod +s", "chmod 777", "chmod 4777",
            "chown root", "sudo su", "sudo bash",
            "/etc/passwd", "/etc/shadow", "/etc/crontab",
            "at.exe", "schtasks", "crontab -e",
        ]

        # HTML / Static file specific
        # Sources: OWASP XSS Prevention Cheat Sheet, OWASP Phishing Prevention,
        # known defacement and phishing HTML patterns
        self.html_keywords = [
            # JavaScript obfuscation inside HTML
            "eval(", "eval (", "eval\t(",
            "string.fromcharcode(", "fromcharcode(",
            "unescape(", "decodeuri(", "decodeuricomponent(",
            "atob(", "btoa(",
            "\\x65\\x76\\x61\\x6c",                 # hex-encoded "eval"
            "\\u0065\\u0076\\u0061\\u006c",           # unicode-encoded "eval"
            "settimeout(", "setinterval(",
            "new function(",

            # Suspicious script src patterns
            "src=http://", "src=https://", 'src ="http', "src ='http",
            "<script src=//", "<script src =", "document.write('<scr",

            # Hidden / invisible iframe (common in defacement & phishing)
            "<iframe", "iframe src=", 'iframe src ="',
            "style=\"display:none", "style='display:none",
            "width=0 height=0", 'width="0" height="0"',
            "visibility:hidden", "opacity:0",
            "position:absolute;top:-", "left:-9999",

            # Redirect tricks
            "window.location=", "window.location.href=",
            "window.location.replace(", "meta http-equiv=\"refresh\"",
            "meta http-equiv='refresh'", "<meta http-equiv=refresh",

            # VBScript (IE-era, still seen in phishing)
            "<script language=\"vbscript\"", "<script language='vbscript'",
            "vbscript:", "activexobject(",
            "createobject(", "wscript.shell",

            # Phishing / credential harvesting patterns
            "<form action=\"http", "<form action='http",
            "action=http://", "method=\"post\"",
            "<input type=\"hidden\"", "type=hidden",
            "password", "username", "login", "signin",
            "document.cookie", "document.getelementbyid('password'",

            # XSS payloads
            "<script>alert(", "javascript:alert(",
            "onerror=", "onload=", "onmouseover=",
            "onclick=javascript:", "href=javascript:",
            "src=javascript:", "img src=x onerror=",
            "<svg onload=", "<body onload=",

            # Base64 embedded blobs in HTML
            "data:text/html;base64,", "data:application/javascript;base64,",
            "data:application/x-javascript;base64,",

            # Remote stylesheet / link injection
            "<link rel=\"stylesheet\" href=\"http",
            "<link rel='stylesheet' href='http",

            # Defacement signatures (common strings)
            "hacked by", "owned by", "defaced by",
            "r00t", "1337", "h4x0r",
        ]
        
    def scan_content(self, content: str, file_ext: str) -> dict:
        """
        Scan content and return a dictionary of triggered keywords.
        Returns {"suspicious": bool, "triggers": list}
        """
        content_lower = content.lower()
        findings = []
        
        # Check OS keywords (applicable to all)
        for kw in self.os_keywords:
            if kw in content_lower:
                findings.append(kw)
                
        # Check language specific
        ext = file_ext.lower()
        if ext == ".php":
            for kw in self.php_keywords:
                if kw in content_lower:
                    findings.append(kw)
        elif ext in [".js", ".ts"]:
            for kw in self.js_keywords:
                if kw in content_lower:
                    findings.append(kw)
        elif ext == ".py":
            for kw in self.python_keywords:
                if kw in content_lower:
                    findings.append(kw)
        elif ext in [".html", ".htm"]:
            for kw in self.html_keywords:
                if kw in content_lower:
                    findings.append(kw)
                    
        return {"suspicious": len(findings) > 0, "triggers": findings}
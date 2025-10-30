"""交互式脚本：将 Zhipu API Key 写入 Windows Credential Manager (keyring)。

使用方法：
    1. 安装依赖：  pip install keyring
    2. 运行：      python mydemo/setup_keyring_api_key.py
    3. 按提示输入密钥（输入时不回显）。
    4. 验证：      python -c "import keyring;print(bool(keyring.get_password('zhipu','api_key')))"

加载顺序（在 multimodal_client.py 中）：
    环境变量 > keyring。

安全提示：
    - keyring 在 Windows 上使用 Credential Manager；密钥不会明文出现在项目文件中。
    - 若需要更新密钥，重新运行本脚本覆盖即可。
"""

import getpass
import sys

try:
    import keyring  # type: ignore
except ImportError:
    print("未安装 keyring。请先执行: pip install keyring", file=sys.stderr)
    sys.exit(1)

SERVICE = "zhipu"
USERNAME = "api_key"

def main():
    print("===== 写入 Zhipu API Key 到本机凭据存储 =====")
    api_key = getpass.getpass("请输入新的 API Key: ")
    if not api_key.strip():
        print("输入为空，已取消。", file=sys.stderr)
        return
    keyring.set_password(SERVICE, USERNAME, api_key.strip())
    print("写入成功。现在可以直接运行: python mydemo/multimodal_client.py")

if __name__ == "__main__":
    main()

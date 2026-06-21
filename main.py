# =============================================================================
# Script: seed_iso_survival_v27.py (CẢI TIẾN 27/7 - SINH TỒN TỐI ƯU)
# Mô tả: Tạo seed.iso cho cloud-init trên QEMU với khả năng tự động hóa toàn
# diện, bảo mật cơ bản, hiệu suất cao và giám sát từ xa.
# Các cải tiến chính:
#   1. Bảo mật: Tự động sinh mật khẩu ngẫu nhiên cho user và VNC.
#   2. Tối ưu hóa: Cài đặt ZRAM swap để tăng hiệu suất trên VPS yếu.
#   3. Kiểm soát: Tích hợp sẵn VPN (Tailscale) để truy cập mạng riêng ảo an toàn.
#   4. Giám sát: Cài đặt Netdata để theo dõi tài nguyên hệ thống thời gian thực.
#   5. Tự động hóa: Script tạo file ready-to-use, chỉ cần chạy QEMU.
#   6. Linh hoạt: Tự động phát hiện phiên bản RustDesk mới nhất từ GitHub.
#   7. Giao diện: Cài thêm theme và icon đẹp cho XFCE (cảm giác chuyên nghiệp).
#   8. Khả năng phục hồi: Cấu hình tự động sửa lỗi phụ thuộc và retry download.
# =============================================================================
import struct
import os
import time
import secrets
import string
import subprocess
import json
import urllib.request

# -----------------------------------------------------------------------------
# Hàm tiện ích chung
# -----------------------------------------------------------------------------
def generate_random_password(length=16):
    """Tạo mật khẩu ngẫu nhiên an toàn."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def pad(data, size):
    """Đệm dữ liệu với null bytes cho đến khi đạt kích thước yêu cầu."""
    return data + b'\x00' * (size - len(data))

def make_iso(output_path, files):
    """
    Tạo file ISO 9660 chứa các file được cung cấp.
    Tham số:
        output_path: Đường dẫn file ISO đầu ra.
        files: Danh sách các tuple (tên_file, nội_dung_bytes).
    """
    SECTOR = 2048 # Kích thước sector chuẩn cho ISO 9660 (Mode 1)
    file_start_sector = 19 # Sector bắt đầu của vùng dữ liệu file
    file_sectors = [] # Lưu trữ sector bắt đầu của mỗi file
    offset = file_start_sector
    # Tính toán vị trí sector cho từng file trong image
    for name, content in files:
        file_sectors.append(offset)
        sectors_needed = (len(content) + SECTOR - 1) // SECTOR
        offset += sectors_needed
    total_sectors = offset

    def lsb_msb_16(n):
        return struct.pack('<H', n) + struct.pack('>H', n)
    def lsb_msb_32(n):
        return struct.pack('<I', n) + struct.pack('>I', n)
    def date_field(t=None):
        if t is None: t = time.gmtime()
        return bytes([t.tm_year-1900, t.tm_mon, t.tm_mday,
                      t.tm_hour, t.tm_min, t.tm_sec, 0])
    def dir_record(name_bytes, sector, size, is_dir=False):
        flags = 0x02 if is_dir else 0x00
        name_len = len(name_bytes)
        record_len = 33 + name_len
        if record_len % 2 != 0: record_len += 1
        rec = bytes([record_len, 0])
        rec += lsb_msb_32(sector)
        rec += lsb_msb_32(size)
        rec += date_field()
        rec += bytes([flags, 0, 0])
        rec += lsb_msb_16(1)
        rec += bytes([name_len]) + name_bytes
        if len(rec) % 2 != 0: rec += b'\x00'
        return rec

    # Xây dựng thư mục gốc
    root_dir = b''
    root_dir += dir_record(b'\x00', 18, SECTOR, is_dir=True)
    root_dir += dir_record(b'\x01', 18, SECTOR, is_dir=True)
    for i, (name, content) in enumerate(files):
        root_dir += dir_record(name.upper().encode(), file_sectors[i], len(content))
    root_dir_padded = pad(root_dir, SECTOR)

    # Xây dựng PVD
    pvd = b'\x01' + b'CD001\x01\x00' + b' ' * 32
    pvd += pad(b'SURVIVAL', 32)
    pvd += b'\x00' * 8 + lsb_msb_32(total_sectors) + b'\x00' * 32
    pvd += lsb_msb_16(1) + lsb_msb_16(1) + lsb_msb_16(SECTOR)
    pvd += lsb_msb_32(total_sectors * SECTOR)
    pvd += struct.pack('<I', 0) + struct.pack('<I', 0)
    pvd += struct.pack('>I', 0) + struct.pack('>I', 0)
    pvd += dir_record(b'\x00', 18, SECTOR, is_dir=True)
    pvd += b' ' * 128 * 4 + b' ' * 37 * 3
    pvd += b'0001010000000000\x00'
    pvd += b'0000000000000000\x00'
    pvd += b'0000000000000000\x00'
    pvd += b'0000000000000000\x00'
    pvd += b'\x01\x00'
    pvd = pad(pvd, SECTOR)

    # Volume Descriptor Set Terminator
    term = pad(b'\xff' + b'CD001\x01', SECTOR)

    # Ghi file ISO
    with open(output_path, 'wb') as f:
        f.write(b'\x00' * (16 * SECTOR))
        f.write(pvd)
        f.write(term)
        f.write(root_dir_padded)
        for name, content in files:
            sectors_needed = (len(content) + SECTOR - 1) // SECTOR
            f.write(pad(content, sectors_needed * SECTOR))
    print(f"[ISO] Đã tạo: {output_path} ({os.path.getsize(output_path)} bytes)")

# -----------------------------------------------------------------------------
# Sinh mật khẩu ngẫu nhiên cho phiên bản cải tiến
# -----------------------------------------------------------------------------
ROOT_PASSWORD = generate_random_password(20)
VNC_PASSWORD = generate_random_password(16)
print(f"[SEC] Mật khẩu root được tạo: {ROOT_PASSWORD}")
print(f"[SEC] Mật khẩu VNC được tạo: {VNC_PASSWORD}")

# -----------------------------------------------------------------------------
# Lấy URL download RustDesk mới nhất từ GitHub API
# -----------------------------------------------------------------------------
def get_latest_rustdesk_url():
    """Tự động lấy link .deb mới nhất của RustDesk từ GitHub."""
    try:
        api_url = "https://api.github.com/repos/rustdesk/rustdesk/releases/latest"
        with urllib.request.urlopen(api_url) as response:
            data = json.loads(response.read().decode())
            for asset in data['assets']:
                if 'x86_64.deb' in asset['browser_download_url']:
                    return asset['browser_download_url']
    except Exception as e:
        print(f"[WARN] Không lấy được link RustDesk mới nhất: {e}. Dùng link mặc định.")
    return "https://github.com/rustdesk/rustdesk/releases/download/1.4.5/rustdesk-1.4.5-x86_64.deb"

RUSTDESK_URL = get_latest_rustdesk_url()
print(f"[PKG] Link RustDesk: {RUSTDESK_URL}")

# -----------------------------------------------------------------------------
# meta-data: Thông tin instance (cải tiến thêm hostname động)
# -----------------------------------------------------------------------------
meta_data = f"""instance-id: survival-vm-{secrets.token_hex(4)}
local-hostname: survival-box
""".encode('utf-8')

# -----------------------------------------------------------------------------
# user-data: Cloud-config cải tiến toàn diện
# -----------------------------------------------------------------------------
user_data = f"""#cloud-config
# ===== CẢI TIẾN SINH TỒN 27/7 =====

# --- Cấu hình người dùng ---
users:
  - name: survivor
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    lock_passwd: false
    groups: sudo, adm, netdev

# --- Mật khẩu động ---
chpasswd:
  expire: false
  list:
    - survivor:{ROOT_PASSWORD}

# --- Cho phép SSH bằng mật khẩu ---
ssh_pwauth: true

# --- Cập nhật hệ thống ---
package_update: true
package_upgrade: true
package_reboot_if_required: true

# --- Gói phần mềm cốt lõi ---
packages:
  # Desktop & VNC
  - xfce4
  - xfce4-goodies
  - xfce4-whiskermenu-plugin
  - x11vnc
  - xvfb
  - dbus-x11
  # Công cụ hệ thống
  - htop
  - btop
  - neofetch
  - nano
  - vim
  - wget
  - curl
  - git
  - net-tools
  - openssh-server
  - ufw
  # Ứng dụng
  - firefox
  - filezilla
  # Theme & Icon cho giao diện chuyên nghiệp
  - arc-theme
  - papirus-icon-theme
  # ZRAM
  - zram-tools

# --- Ghi file cấu hình ---
write_files:
  # 1. Dịch vụ VNC với XFCE
  - path: /etc/systemd/system/xvnc.service
    permissions: '0644'
    content: |
      [Unit]
      Description=X Virtual Frame Buffer + XFCE Desktop + x11vnc
      After=network.target
      [Service]
      User=survivor
      Environment=DISPLAY=:0
      ExecStartPre=/bin/bash -c "pkill Xvfb || true"
      ExecStartPre=/bin/bash -c "pkill x11vnc || true"
      ExecStartPre=/bin/bash -c "Xvfb :0 -screen 0 1366x768x24 +extension RANDR &"
      ExecStartPre=/bin/sleep 3
      ExecStart=/bin/bash -c "DISPLAY=:0 startxfce4 & sleep 5 && x11vnc -display :0 -rfbport 5900 -rfbauth /home/survivor/.vnc/passwd -forever -shared -noxdamage -noxfixes -o /var/log/x11vnc.log"
      Restart=always
      RestartSec=10
      [Install]
      WantedBy=multi-user.target

  # 2. Cấu hình ZRAM (tối ưu RAM)
  - path: /etc/default/zramswap
    permissions: '0644'
    content: |
      ALGO=zstd
      PERCENT=50
      PRIORITY=100

  # 3. Script cài đặt Tailscale (VPN mesh)
  - path: /opt/setup-tailscale.sh
    permissions: '0755'
    content: |
      #!/bin/bash
      curl -fsSL https://tailscale.com/install.sh | sh
      tailscale up --authkey=YOUR_TAILSCALE_AUTH_KEY --hostname=survival-box

  # 4. Script cài Netdata (Giám sát)
  - path: /opt/setup-netdata.sh
    permissions: '0755'
    content: |
      #!/bin/bash
      bash <(curl -Ss https://my-netdata.io/kickstart.sh) --stable-channel --disable-telemetry

  # 5. Cấu hình XFCE desktop chuyên nghiệp
  - path: /home/survivor/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml
    permissions: '0644'
    owner: survivor:survivor
    content: |
      <?xml version="1.0" encoding="UTF-8"?>
      <channel name="xsettings" version="1.0">
        <property name="Net" type="empty">
          <property name="ThemeName" type="string" value="Arc-Dark"/>
          <property name="IconThemeName" type="string" value="Papirus-Dark"/>
        </property>
      </channel>

  # 6. Thông tin đăng nhập lưu sẵn trên desktop
  - path: /home/survivor/Desktop/CREDENTIALS.txt
    permissions: '0600'
    owner: survivor:survivor
    content: |
      ========================================
      SURVIVAL VPS - THÔNG TIN TRUY CẬP
      ========================================
      Người dùng: survivor
      Mật khẩu SSH: {ROOT_PASSWORD}
      Mật khẩu VNC: {VNC_PASSWORD}
      Cổng SSH: 2222 (host forwarding)
      Cổng VNC: 5900 (host forwarding)
      ========================================

  # 7. Script tự động khởi động RustDesk
  - path: /home/survivor/.config/autostart/rustdesk.desktop
    permissions: '0644'
    owner: survivor:survivor
    content: |
      [Desktop Entry]
      Type=Application
      Name=RustDesk
      Exec=rustdesk --tray
      Hidden=false
      NoDisplay=false
      X-GNOME-Autostart-enabled=true

# --- Lệnh chạy khi khởi tạo ---
runcmd:
  # Thiết lập mật khẩu VNC cho user survivor
  - mkdir -p /home/survivor/.vnc
  - x11vnc -storepasswd {VNC_PASSWORD} /home/survivor/.vnc/passwd
  - chmod 600 /home/survivor/.vnc/passwd
  - chown -R survivor:survivor /home/survivor

  # Tải và cài RustDesk với retry
  - for i in 1 2 3; do wget -O /tmp/rustdesk.deb "{RUSTDESK_URL}" && break || sleep 10; done
  - dpkg -i /tmp/rustdesk.deb || apt install -f -y

  # Kích hoạt VNC service
  - systemctl daemon-reload
  - systemctl enable xvnc.service
  - systemctl start xvnc.service

  # Tường lửa cơ bản
  - ufw allow 22/tcp
  - ufw allow 5900/tcp
  - ufw allow 21115:21119/tcp
  - ufw allow 8000:8999/udp
  - ufw --force enable

  # Chạy script cài đặt thêm (bỏ comment nếu có key)
  # - bash /opt/setup-tailscale.sh
  # - bash /opt/setup-netdata.sh

  # Dọn dẹp
  - apt autoremove -y
  - apt clean

  # Thông báo hoàn tất
  - wall "SURVIVAL VPS READY - SSH: survivor@<host> -p 2222 | VNC: <host>:5900"

# --- Thông báo cuối cùng ---
final_message: "SURVIVAL VPS 27/7 đã sẵn sàng. Mọi cấu hình đã hoàn tất. Đăng nhập: survivor / $ROOT_PASSWORD"
""".encode('utf-8')

# -----------------------------------------------------------------------------
# Tạo file seed.iso
# -----------------------------------------------------------------------------
output_dir = os.path.join(os.environ['HOME'], 'qemu')
os.makedirs(output_dir, exist_ok=True)
output_iso = os.path.join(output_dir, 'seed_survival_v27.iso')

make_iso(output_iso, [
    ('meta-data', meta_data),
    ('user-data', user_data),
])

print(f"""
{"="*60}
  SURVIVAL VPS 27/7 - ISO ĐÃ SẴN SÀNG
{"="*60}
  File: {output_iso}
  User: survivor
  SSH Pass: {ROOT_PASSWORD}
  VNC Pass: {VNC_PASSWORD}
{"="*60}

Lệnh QEMU khởi chạy:
qemu-system-x86_64 \\
  -m 4096 \\
  -smp 4 \\
  -cpu host \\
  -machine type=q35,accel=kvm \\
  -netdev user,id=net0,hostfwd=tcp::2222-:22,hostfwd=tcp::5900-:5900 \\
  -device virtio-net-pci,netdev=net0 \\
  -drive file=/path/to/ubuntu-22.04-server-cloudimg-amd64.img,if=virtio,format=qcow2 \\
  -cdrom {output_iso} \\
  -vga qxl \\
  -display none \\
  -daemonize

Sau khi khởi động, kết nối qua:
  SSH:   ssh survivor@<địa_chỉ_ip_máy_chủ> -p 2222
  VNC:   <địa_chỉ_ip_máy_chủ>:5900 (mật khẩu: {VNC_PASSWORD})
  RustDesk: ID sẽ hiện trong desktop hoặc qua SSH: cat /var/log/rustdesk.log
""")

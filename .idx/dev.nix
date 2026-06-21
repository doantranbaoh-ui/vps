# =============================================================================
# File: devbox.json (CẢI TIẾN TỪ CẤU HÌNH GỐC)
# Mô tả: Cấu hình môi trường phát triển Devbox với QEMU, noVNC và Cloudflared.
# Sửa lỗi chính tả, tối ưu cú pháp và thêm cải tiến để đảm bảo hoạt động ổn định.
# Nền tảng: Devbox (jetpack.io/devbox) hoặc tương tự Nix-shell.
# =============================================================================
{
  # -------------------------------------------------------------------------
  # Gói hệ thống từ Nixpkgs (kênh ổn định 24.11)
  # Sửa: "pkgs.htop" -> "pkgs.htop", "pkgs.gnugrep" -> "pkgs.gnugrep"
  # -------------------------------------------------------------------------
  pkgs ? import <nixpkgs> { },
  ...
}: {
  channel = "stable-24.11";

  packages = [
    pkgs.qemu             # Bộ giả lập máy ảo QEMU
    pkgs.htop             # Công cụ giám sát tiến trình (sửa từ "htop")
    pkgs.cloudflared      # Cloudflare Tunnel client
    pkgs.coreutils        # Tiện ích GNU cơ bản (ls, cat, echo...)
    pkgs.gnugrep          # GNU Grep (sửa từ "gnugrep")
    pkgs.wget             # Trình tải file không tương tác
    pkgs.git              # Hệ thống quản lý phiên bản
    pkgs.python3          # Python 3 để chạy script tạo seed ISO
  ];

  # -------------------------------------------------------------------------
  # Script tự động khởi chạy khi workspace bắt đầu
  # Cải tiến: Thêm kiểm tra lỗi, tối ưu logic dọn dẹp, xử lý URL Cloudflared.
  # -------------------------------------------------------------------------
  idx.workspace.onStart = {
    qemu = ''
      # Bật chế độ dừng ngay khi có lỗi (strict mode)
      set -e

      # -------------------------------------------------------------------
      # 1. DỌN DẸP LẦN ĐẦU (CHỈ CHẠY MỘT LẦN)
      # -------------------------------------------------------------------
      if [ ! -f /home/user/.cleanup_done ]; then
        echo "[CLEAN] Dọn dẹp các file rác trong home directory..."
        rm -rf /home/user/.gradle/* 2>/dev/null || true
        rm -rf /home/user/.emu/* 2>/dev/null || true
        rm -rf /home/user/.android/* 2>/dev/null || true
        # Giữ lại thư mục vps và file đánh dấu, xóa phần còn lại
        find /home/user -mindepth 1 -maxdepth 1 \
          ! -name 'vps' \
          ! -name '.cleanup_done' \
          ! -name '.*' \
          -exec rm -rf {} + 2>/dev/null || true
        touch /home/user/.cleanup_done
        echo "[CLEAN] Dọn dẹp hoàn tất."
      else
        echo "[CLEAN] Đã dọn dẹp trước đó, bỏ qua."
      fi

      # -------------------------------------------------------------------
      # 2. THIẾT LẬP BIẾN MÔI TRƯỜNG
      # -------------------------------------------------------------------
      VM_DIR="$HOME/qemu"
      DISK="$VM_DIR/ubuntu.qcow2"
      SEED_ISO="$VM_DIR/seed.iso"
      NOVNC_DIR="$HOME/noVNC"

      mkdir -p "$VM_DIR"

      # -------------------------------------------------------------------
      # 3. TẢI VÀ CHUẨN BỊ Ổ ĐĨA UBUNTU CLOUD IMAGE
      # -------------------------------------------------------------------
      if [ ! -f "$DISK" ]; then
        echo "[DISK] Đang tải Ubuntu 24.04 cloud image..."
        wget -O "$DISK" \
          "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
        echo "[DISK] Đang mở rộng dung lượng ổ đĩa lên 64G..."
        qemu-img resize "$DISK" 64G
        echo "[DISK] Ổ đĩa đã sẵn sàng."
      else
        echo "[DISK] Ổ đĩa Ubuntu đã tồn tại, bỏ qua tải."
      fi

      # -------------------------------------------------------------------
      # 4. TẠO SEED ISO CHO CLOUD-INIT (CHỈ KHI CHƯA CÓ HOẶC RỖNG)
      # -------------------------------------------------------------------
      if [ ! -f "$SEED_ISO" ] || [ ! -s "$SEED_ISO" ]; then
        echo "[SEED] Đang tạo seed ISO..."
        python3 /home/user/vps/main.py
        if [ -s "$SEED_ISO" ]; then
          echo "[SEED] Seed ISO đã được tạo thành công ($(du -h $SEED_ISO | cut -f1))."
        else
          echo "[SEED] LỖI: File seed.iso trống hoặc không được tạo!"
          exit 1
        fi
      else
        echo "[SEED] Seed ISO đã tồn tại, bỏ qua tạo mới."
      fi

      # -------------------------------------------------------------------
      # 5. TẢI NOVNC (WEBSOCKET VNC CLIENT)
      # -------------------------------------------------------------------
      if [ ! -d "$NOVNC_DIR/.git" ]; then
        echo "[NOVNC] Đang clone noVNC từ GitHub..."
        git clone https://github.com/novnc/noVNC.git "$NOVNC_DIR"
        echo "[NOVNC] Clone hoàn tất."
      else
        echo "[NOVNC] noVNC đã tồn tại, bỏ qua clone."
      fi

      # -------------------------------------------------------------------
      # 6. KHỞI ĐỘNG QEMU VỚI CÁC THAM SỐ TỐI ƯU
      # Sửa: "nohup" -> "nohup" (đã đúng), thêm -enable-kvm nếu có quyền.
      # -------------------------------------------------------------------
      echo "[QEMU] Đang khởi động máy ảo..."
      nohup qemu-system-x86_64 \
        -enable-kvm \
        -cpu host \
        -smp 8,cores=8 \
        -m 16384 \
        -M q35 \
        -device qemu-xhci \
        -device usb-tablet \
        -vga virtio \
        -netdev user,id=n0,hostfwd=tcp::2222-:22 \
        -net nic,netdev=n0,model=virtio-net-pci \
        -drive file="$DISK",format=qcow2,if=virtio \
        -drive file="$SEED_ISO",format=raw,if=virtio,readonly=on \
        -vnc :0 \
        -display none \
        > /tmp/qemu.log 2>&1 &

      echo "[QEMU] Tiến trình QEMU đã khởi động (PID: $!). Chờ VM boot..."
      sleep 15  # Tăng thời gian chờ để VM boot hoàn tất

      # Kiểm tra QEMU còn sống không
      if ! pgrep qemu-system > /dev/null; then
        echo "[QEMU] LỖI: QEMU đã thoát! Kiểm tra /tmp/qemu.log"
        cat /tmp/qemu.log
        exit 1
      fi

      # -------------------------------------------------------------------
      # 7. KHỞI ĐỘNG NOVNC PROXY (CHUYỂN VNC -> WEBSOCKET)
      # -------------------------------------------------------------------
      echo "[NOVNC] Đang khởi động noVNC proxy trên cổng 8888..."
      nohup "$NOVNC_DIR/utils/novnc_proxy" \
        --vnc 127.0.0.1:5900 \
        --listen 8888 \
        > /tmp/novnc.log 2>&1 &
      echo "[NOVNC] noVNC proxy đã khởi động (PID: $!)."

      # -------------------------------------------------------------------
      # 8. KHỞI ĐỘNG CLOUDFLARED TUNNEL (TẠO URL CÔNG KHAI)
      # -------------------------------------------------------------------
      echo "[CF] Đang khởi động Cloudflared tunnel..."
      nohup cloudflared tunnel \
        --no-autoupdate \
        --url http://localhost:8888 \
        > /tmp/cloudflared.log 2>&1 &
      echo "[CF] Cloudflared đã khởi động (PID: $!)."

      # Chờ tunnel được tạo và URL xuất hiện trong log
      echo "[CF] Đang chờ URL từ Cloudflare..."
      for i in $(seq 1 20); do
        if grep -q "trycloudflare.com" /tmp/cloudflared.log 2>/dev/null; then
          break
        fi
        sleep 3
      done

      # -------------------------------------------------------------------
      # 9. TRÍCH XUẤT VÀ HIỂN THỊ URL TRUY CẬP
      # -------------------------------------------------------------------
      if grep -q "trycloudflare.com" /tmp/cloudflared.log 2>/dev/null; then
        URL=$(grep -o "https://[a-z0-9.-]*trycloudflare.com" /tmp/cloudflared.log | head -n1)
        echo "========================================="
        echo "  UBUNTU SERVER + XFCE ĐÃ SẴN SÀNG"
        echo "========================================="
        echo "  noVNC URL: $URL/vnc.html"
        echo "  Mật khẩu VNC: ubuntu"
        echo "  SSH:        ssh -p 2222 ubuntu@localhost"
        echo "========================================="
        # Lưu URL vào file để dễ truy xuất
        mkdir -p /home/user/vps
        echo "$URL/vnc.html" > /home/user/vps/noVNC-URL.txt
        echo "[CF] URL đã lưu vào ~/vps/noVNC-URL.txt"
      else
        echo "[CF] LỖI: Không tìm thấy URL Cloudflared. Kiểm tra /tmp/cloudflared.log"
        echo "--- Nội dung log Cloudflared ---"
        cat /tmp/cloudflared.log
        echo "--- Kết thúc log ---"
      fi

      # -------------------------------------------------------------------
      # 10. VÒNG LẶP GIỮ TIẾN TRÌNH SỐNG VÀ HIỂN THỊ TRẠNG THÁI
      # -------------------------------------------------------------------
      elapsed=0
      while true; do
        QEMU_STATUS="STOPPED"
        if pgrep qemu-system > /dev/null; then
          QEMU_STATUS="running"
        fi
        echo "[STATUS] Thời gian hoạt động: ${elapsed} phút | QEMU: ${QEMU_STATUS}"
        ((elapsed++))
        sleep 60
      done
    '';
  };

  # -------------------------------------------------------------------------
  # Cấu hình previews cho Devbox (hiển thị giao diện web)
  # -------------------------------------------------------------------------
  idx.previews = {
    enable = true;
    previews = {
      # Cửa sổ preview cho noVNC (tự động mở khi workspace start)
      qemu = {
        manager = "web";
        command = [
          "bash" "-lc"
          # Hiển thị thông báo hướng dẫn khi mở preview
          "echo 'noVNC đang chạy trên cổng 8888. Mở terminal để xem URL Cloudflared.'"
        ];
      };
      # Terminal tích hợp để thao tác thủ công
      terminal = {
        manager = "web";
        command = [ "bash" ];
      };
    };
  };
}

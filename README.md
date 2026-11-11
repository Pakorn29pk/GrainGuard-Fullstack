# GrainGuard Full-stack

Dashboard และหน้า Login ของ GrainGuard พร้อม Hub, ระบบบัญชีแยกโรงสี และตัวเปิดแอปบน Raspberry Pi Desktop ชุดนี้รวมเลย์เอาต์ Overview เวอร์ชันล่าสุดบน Pi4 ซึ่งใช้ร่วมกันระหว่าง Local และ Online

## เปิด Preview

ติดตั้ง Python 3.11 ขึ้นไป แล้วโคลน repo

```sh
git clone https://github.com/Panupon777/GrainGuard-Fullstack.git
cd GrainGuard-Fullstack
```

- Windows ดับเบิลคลิก `START_PREVIEW.cmd` ระบบจะติดตั้ง dependencies ในครั้งแรก
- Linux หรือ macOS รันคำสั่งด้านล่างจากโฟลเดอร์ repo

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-preview.txt
.venv/bin/python start_preview.py
```

เปิด [Local สำหรับจัดการ](http://127.0.0.1:8886/login/local.html) หรือ [Online สำหรับดูข้อมูล](http://127.0.0.1:8887/login/online.html) ทั้งสองลิงก์เปิดจากเครื่องที่รัน Preview

| บัญชีทดสอบ | Username | Password สำหรับ Preview |
| --- | --- | --- |
| เดโม 1 เครื่อง | `pumpkintec` | `preview-only-2026` |
| โรงสีจำลอง 6 เครื่อง | `uengliangseng` | `preview-only-2026` |

Preview สร้างบัญชีและข้อมูลจำลองใหม่ในโฟลเดอร์ชั่วคราวทุกครั้ง กด Ctrl+C เพื่อปิด

## แก้ไขและทดสอบ

| ส่วน | โฟลเดอร์ |
| --- | --- |
| Dashboard และหน้า Login | `dashboard/` และ `dashboard/login/` |
| Hub, API และระบบบัญชี | `hub-core/grainguard_hub/` |
| ตัวเปิดแอปและไอคอนบน Pi | `pi-desktop/` |
| ข้อมูลจำลองและชุดทดสอบ | `sim/`, `tests/` และไฟล์ `*.cjs` ใน Dashboard |

รันคำสั่งจากโฟลเดอร์ repo หลังเปิดใช้งาน venv

```sh
python -m pip install -r hub-core/requirements-dev.txt httpx
python -m pytest
node --test dashboard/*.cjs dashboard/login/*.cjs
```

ดูผลตรวจเลย์เอาต์ล่าสุดใน [รายงาน UIAudit](review/UIAUDIT_TH.md)

## ส่งงานกลับมาอัปเดต Pi4

แยก branch จาก `main` แล้วเปิด Pull Request พร้อมสรุปที่แก้และผลทดสอบ Local กับ Online สำหรับเทียบไฟล์บน Pi4 ให้ดูรุ่นและ SHA-256 ใน `PI_RUNTIME_SHA256.json` ตัวเริ่มบริการบน Pi คือ `run_pi.py` และใช้ฐานข้อมูลกับค่าบริการที่อยู่บน Pi4 อยู่แล้ว

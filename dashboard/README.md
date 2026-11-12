---
title: วิธีใช้และอัปเดต Stable Income Dashboard
type: instruction
created: 2026-11-12
updated: 2026-11-12
tags: [dashboard, dividend]
sources: [https://finance.yahoo.com, https://www.thaibma.or.th/EN/Market/YieldCurve/Government.aspx, https://www.set.or.th]
status: draft
---

# Stable Income Dashboard

ผลงาน (เปิดดูได้เลย): https://santichins.github.io/aIa-hw-Bee/output/dashboard.html

ข้อมูลมาจาก Yahoo Finance (แหล่งรอง) ยังไม่ตรวจกับ set.or.th `[ยังไม่ยืนยัน]` ใช้เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน

## 2 วิธีอัปเดตข้อมูล

**1) บน GitHub (ไม่ต้องติดตั้งอะไร)**
- ระบบอัปเดตอัตโนมัติ 10:30 น. (เวลาไทย) วันจันทร์-ศุกร์ โดย GitHub Actions
- อยากสั่งเอง: แท็บ **Actions** > **Update dashboard** > **Run workflow** (ต้องล็อกอินเป็นเจ้าของ repo) ใช้เวลาราว 2–5 นาที แล้วรีเฟรชหน้าผลงาน
- ปุ่ม **Update (GitHub Actions)** บนหน้าผลงานพาไปหน้า Run workflow นี้

**2) ในเครื่องของคุณ (ปุ่ม Update ในหน้าเว็บทำงานเอง)**

```bash
git clone https://github.com/santichins/aIa-hw-Bee.git
cd aIa-hw-Bee
python3 dashboard/serve.py
```

เปิด http://127.0.0.1:8765 แล้วกด **Update ข้อมูล** (ใช้ Python 3 อย่างเดียว ไม่ต้องติดตั้งแพ็กเกจเพิ่ม) server ผูกกับ 127.0.0.1 เท่านั้น

## ไฟล์

- `build_dashboard.py` ดึงข้อมูล Yahoo คำนวณตัวชี้วัด และฝังลง `template.html` → `dashboard/index.html`
- `serve.py` server ในเครื่องสำหรับปุ่ม Update
- `tickers.txt` หุ้นที่จัดกลุ่มธุรกิจ · `../data/universe.json` รายชื่อหุ้นทั้งตลาด (เฉพาะชื่อย่อ) · `../data/th10y.json` พันธบัตร 10 ปี (ThaiBMA) · `../data/sethd.json` สมาชิก SETHD (SET)
- `../.github/workflows/update.yml` ตั้งเวลาอัปเดต

## ข้อจำกัด

- Yahoo ให้งบรายปีย้อนหลังประมาณ 4 ปี ค่า CV และ payout ดูได้จำกัด
- Yahoo อาจบล็อกหรือจำกัดคำขอจาก GitHub ถ้า workflow ล้มเหลว หน้าผลงานจะคงข้อมูลชุดเดิมไว้
- ตัวเลขทั้งหมดเป็น `[ยังไม่ยืนยัน]` จนกว่าจะสุ่มตรวจกับ set.or.th

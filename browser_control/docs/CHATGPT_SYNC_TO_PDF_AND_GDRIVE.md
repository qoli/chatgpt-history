# ChatGPT Projects 增量同步到 Markdown

這個流程現在只做一件事：

1. 同步所有 ChatGPT Projects 的 conversations 到穩定的 Markdown 目錄

腳本位置：

```bash
browser_control/scripts/sync_chatgpt_projects_to_pdf_and_gdrive.py
```

## 設計重點

- 使用 `playwright-cli + Arc CDP`
- 直接借用你目前已登入 Arc 的 ChatGPT session
- 自動跳過「本地已存在且 `update_time` 未變動」的 conversations
- 只保留 Markdown 穩定鏡像與增量狀態檔

## 預設輸出

Markdown 穩定鏡像：

```bash
browser_control/output/chatgpt_markdown
```

增量狀態檔：

```bash
browser_control/output/chatgpt_markdown/sync_state.json
```

## 基本用法

全量跑一次：

```bash
python3 browser_control/scripts/sync_chatgpt_projects_to_pdf_and_gdrive.py
```

只同步特定 project：

```bash
python3 browser_control/scripts/sync_chatgpt_projects_to_pdf_and_gdrive.py --project eisonAI
python3 browser_control/scripts/sync_chatgpt_projects_to_pdf_and_gdrive.py --project Syncnext
```

先做小量驗證：

```bash
python3 browser_control/scripts/sync_chatgpt_projects_to_pdf_and_gdrive.py \
  --project eisonAI \
  --limit-conversations 1
```

強制重抓全部 matched conversations：

```bash
python3 browser_control/scripts/sync_chatgpt_projects_to_pdf_and_gdrive.py --force-refresh
```

若也想保留 raw JSON：

```bash
python3 browser_control/scripts/sync_chatgpt_projects_to_pdf_and_gdrive.py --save-json
```

## 增量跳過規則

對每個 conversation，腳本會檢查：

- `sync_state.json` 裡記錄的 `update_time`
- 對應 Markdown 檔案是否存在

若本地已存在且 `update_time` 沒變，就跳過重新抓取，直接沿用本地 Markdown。

## 目前狀態

- PDF 轉換邏輯已移除
- `rclone` / Google Drive 同步邏輯已移除
- 這個入口目前只負責 Markdown 增量同步

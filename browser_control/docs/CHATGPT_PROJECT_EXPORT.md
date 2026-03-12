# ChatGPT Project Markdown Export（playwright-cli + Arc CDP）

本文件說明如何在「你已登入 Arc 的 ChatGPT session」上，導出所有 ChatGPT Projects 的對話為 Markdown。

此方案參考本地 `ChatGPT-Exporter` 專案的 API 路徑與對話轉換思路，但不安裝瀏覽器擴充。流程改為：

1. 用 `playwright-cli + Arc CDP` 借用你目前已登入的 ChatGPT session
2. 讀取 access token / device id
3. 直接呼叫 ChatGPT backend API
4. 把每個 project 的 conversations 輸出成 Markdown

## 前置條件

- Arc 已以 CDP 模式啟動
- 你已在 Arc 登入 ChatGPT
- 已安裝 `playwright-cli`

確認：

```bash
playwright-cli --version
curl -s http://127.0.0.1:9222/json/version
```

若 Arc 尚未開啟 CDP：

```bash
open -a "Arc" --args --remote-debugging-port=9222 --remote-allow-origins='*'
```

## 固定 config

本 repo 固定使用：

```bash
browser_control/config/playwright-arc-cdp-local-9222.json
```

## 腳本位置

```bash
browser_control/scripts/export_chatgpt_projects_markdown.py
```

## 基本用法

列出你目前帳號下可見的 ChatGPT Projects：

```bash
python3 browser_control/scripts/export_chatgpt_projects_markdown.py --list-projects
```

導出全部 project conversations：

```bash
python3 browser_control/scripts/export_chatgpt_projects_markdown.py
```

只導出指定 project：

```bash
python3 browser_control/scripts/export_chatgpt_projects_markdown.py --project eisonAI
python3 browser_control/scripts/export_chatgpt_projects_markdown.py --project Syncnext
```

同時導出多個 project：

```bash
python3 browser_control/scripts/export_chatgpt_projects_markdown.py --project eisonAI --project Syncnext
```

先小量驗證，只抓每個 project 前 1 條 conversation：

```bash
python3 browser_control/scripts/export_chatgpt_projects_markdown.py --limit-projects 2 --limit-conversations 1
```

若也想保留 raw conversation JSON：

```bash
python3 browser_control/scripts/export_chatgpt_projects_markdown.py --save-json
```

## 輸出位置

預設輸出到：

```bash
browser_control/output/chatgpt_exports/<timestamp>/
```

目錄結構類似：

```text
browser_control/output/chatgpt_exports/20260312-101500/
  manifest.json
  eisonAI/
    某個對話_xxxxxxxx.md
  Syncnext/
    某個對話_yyyyyyyy.md
```

`manifest.json` 會記錄本次導出的 project 與 conversation 清單。

## 重要說明

- 腳本會自動建立一個 named `playwright-cli` session：`chatgpt_export`
- 腳本不會要求你重新登入 ChatGPT
- 腳本不會把資料送到第三方服務
- access token / cookie 很敏感；不要把命令輸出貼到公開地方
- 這套做法依賴 ChatGPT 內部 backend API，OpenAI 改站內接口時可能需要調整腳本

## 常見用法

只看 project 名稱：

```bash
python3 browser_control/scripts/export_chatgpt_projects_markdown.py --list-projects
```

導出 `eisonAI` 全部 conversations：

```bash
python3 browser_control/scripts/export_chatgpt_projects_markdown.py --project eisonAI
```

導出 `eisonAI` 與 `Syncnext`，每個 project 先抓 3 條做驗證：

```bash
python3 browser_control/scripts/export_chatgpt_projects_markdown.py \
  --project eisonAI \
  --project Syncnext \
  --limit-conversations 3
```

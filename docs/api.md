# API

## 作成

```http
POST /api/projects
```

```json
{
  "title": "土地があっても、銀行は貸さない",
  "prompt": "中小企業経営者向けに、消費税が資金繰りを圧迫する現実を伝える",
  "duration": 60,
  "style": "serious_documentary",
  "model": "mock",
  "subtitle": true,
  "bgm": false
}
```

## 状態確認

```http
GET /api/projects/{project_id}/status
```

## ダウンロード

```http
GET /api/projects/{project_id}/download
```

"""מרכיב את קובץ ה-workflow ל-n8n מתוך הפרומפטים שב-prompts/.

מריצים אחרי כל שינוי בפרומפט:  python build_workflow.py
"""
import io, json, re

EPISODE = {
    "url": "https://dts.podtrac.com/redirect.mp3/cdn.simplecast.com/media/audio/transcoded/"
           "a0bcaa21-99d1-482d-9833-feb3aaf9e31c/d3e99393-a86b-4bf5-ae97-7b5194be2228/episodes/"
           "audio/group/f6cf85c6-b496-4890-a02e-b9225ef55544/group-item/"
           "c06f7da1-2a1f-4120-8cea-e20cdb7d7b2d/128_default_tc.mp3",
    "title": "חושבים טוב 212",
    "bytes": "82658133",
}
MODEL = "gemini-2.5-flash"
MAILBOX = "SENDER@example.com"


def prompt(path):
    """שולף את גוף הפרומפט מתוך גוש ה-``` בקובץ המרקדאון."""
    return re.search(r"```\n(.*?)\n```", io.open(path, encoding="utf-8").read(), re.S).group(1).strip()


TEXT = "candidates[0].content.parts.filter(p => p.text).map(p => p.text).join('')"
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
AUTH = {"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"}


def node(name, type_, ver, pos, params, **extra):
    return {"id": name, "name": name, "type": type_, "typeVersion": ver,
            "position": pos, "parameters": params, **extra}


def assign(pairs):
    return {"assignments": {"assignments": [
        {"id": str(i), "name": k, "value": v, "type": "string"}
        for i, (k, v) in enumerate(pairs)]}, "options": {}}


nodes = [
    node("Manual Trigger", "n8n-nodes-base.manualTrigger", 1, [0, 0], {}),

    node("Setup", "n8n-nodes-base.set", 3.4, [200, 0], assign([
        ("episodeUrl", EPISODE["url"]),
        ("episodeTitle", EPISODE["title"]),
        ("episodeBytes", EPISODE["bytes"]),
        ("model", MODEL),
        ("mailbox", MAILBOX),
        ("promptTranscribe", prompt("prompts/01-transcription.md")),
        ("promptSummary", prompt("prompts/02-summary.md")),
    ])),

    # פותח העלאה מתחדשת ומקבל בחזרה כתובת העלאה חד-פעמית בכותרת התגובה
    node("Start Upload", "n8n-nodes-base.httpRequest", 4.2, [400, 0], {
        **AUTH,
        "method": "POST",
        "url": f"{GEMINI}/files",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "X-Goog-Upload-Protocol", "value": "resumable"},
            {"name": "X-Goog-Upload-Command", "value": "start"},
            {"name": "X-Goog-Upload-Header-Content-Length",
             "value": "={{ $json.episodeBytes }}"},
            {"name": "X-Goog-Upload-Header-Content-Type", "value": "audio/mpeg"},
        ]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ file: { display_name: $json.episodeTitle } }) }}",
        "options": {"response": {"response": {"fullResponse": True}}},
    }),

    # מוריד את ה-MP3 עצמו. חייב לרוץ אחרי Start Upload כדי שהקובץ יהיה על הפריט שנכנס להעלאה
    node("Download Episode", "n8n-nodes-base.httpRequest", 4.2, [600, 0], {
        "url": "={{ $('Setup').first().json.episodeUrl }}",
        "options": {"response": {"response": {"responseFormat": "file",
                                              "outputPropertyName": "data"}},
                    "timeout": 600000},
    }),

    node("Finish Upload", "n8n-nodes-base.httpRequest", 4.2, [800, 0], {
        "method": "POST",
        "url": "={{ $('Start Upload').first().json.headers['x-goog-upload-url'] }}",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "X-Goog-Upload-Offset", "value": "0"},
            {"name": "X-Goog-Upload-Command", "value": "upload, finalize"},
        ]},
        "sendBody": True,
        "contentType": "binaryData",
        "inputDataFieldName": "data",
        "options": {"timeout": 900000},
    }),

    # retryOnFail מכסה את הפער שבו Gemini עדיין מעבד את הקובץ ומחזיר שגיאה
    node("Transcribe", "n8n-nodes-base.httpRequest", 4.2, [1000, 0], {
        **AUTH,
        "method": "POST",
        "url": f"={GEMINI}/models/{{{{ $('Setup').first().json.model }}}}:generateContent",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ contents: [{ parts: ["
                    "{ text: $('Setup').first().json.promptTranscribe }, "
                    "{ file_data: { mime_type: 'audio/mpeg', file_uri: $json.file.uri } }"
                    "] }], generationConfig: { temperature: 0.2, maxOutputTokens: 65536 } }) }}",
        "options": {"timeout": 1800000},
    }, retryOnFail=True, maxTries=5, waitBetweenTries=20000),

    node("Summarize", "n8n-nodes-base.httpRequest", 4.2, [1200, 0], {
        **AUTH,
        "method": "POST",
        "url": f"={GEMINI}/models/{{{{ $('Setup').first().json.model }}}}:generateContent",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ contents: [{ parts: [{ text: "
                    "$('Setup').first().json.promptSummary + '\n\n' + $json." + TEXT +
                    " }] }], generationConfig: { temperature: 0.3, maxOutputTokens: 16384 } }) }}",
        "options": {"timeout": 900000},
    }, retryOnFail=True, maxTries=3, waitBetweenTries=15000),

    node("Collect", "n8n-nodes-base.set", 3.4, [1400, 0], assign([
        ("title", "={{ $('Setup').first().json.episodeTitle }}"),
        ("transcript", "={{ $('Transcribe').first().json." + TEXT + " }}"),
        ("summary", "={{ $json." + TEXT + " }}"),
    ])),

    node("Summary To HTML", "n8n-nodes-base.markdown", 1, [1600, 0], {
        "mode": "markdownToHtml",
        "markdown": "={{ $json.summary }}",
        "destinationKey": "summaryHtml",
        "options": {},
    }),

    node("Transcript To File", "n8n-nodes-base.convertToFile", 1.1, [1800, 0], {
        "operation": "toText",
        "sourceProperty": "transcript",
        "options": {"fileName": "transcript.txt", "encoding": "utf8"},
    }),

    node("Send Email", "n8n-nodes-base.emailSend", 2.1, [2000, 0], {
        "fromEmail": "={{ $('Setup').first().json.mailbox }}",
        "toEmail": "={{ $('Setup').first().json.mailbox }}",
        "subject": "={{ $('Collect').first().json.title }}",
        "emailFormat": "html",
        "html": "={{ $('Summary To HTML').first().json.summaryHtml }}",
        "options": {"attachments": "data"},
    }),
]

order = [n["name"] for n in nodes]
connections = {a: {"main": [[{"node": b, "type": "main", "index": 0}]]}
               for a, b in zip(order, order[1:])}

workflow = {"name": "פודקאסט → סיכום למייל", "nodes": nodes,
            "connections": connections, "settings": {"executionOrder": "v1"}}

io.open("n8n-workflow.json", "w", encoding="utf-8", newline="\n").write(
    json.dumps(workflow, ensure_ascii=False, indent=2))
print(f"נכתב n8n-workflow.json — {len(nodes)} תחנות")

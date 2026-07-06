const express = require("express");
const qrcodeTerminal = require("qrcode-terminal");
const qrcode = require("qrcode");
const { Client, LocalAuth } = require("whatsapp-web.js");

const PORT = process.env.PORT || 8090;
const TOKEN = process.env.WHATSAPP_RELAY_TOKEN || "";
const DEFAULT_GROUP_ID = process.env.WHATSAPP_GROUP_ID || "";

const app = express();
app.use(express.json({ limit: "2mb" }));

let isReady = false;
let latestQr = "";
let latestQrDataUrl = "";
let latestQrAt = null;

const client = new Client({
  authStrategy: new LocalAuth({
    dataPath: "/opt/hrguru-whatsapp-relay/.wwebjs_auth"
  }),
  puppeteer: {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--disable-extensions",
      "--disable-background-networking",
      "--disable-sync",
      "--disable-default-apps",
      "--no-first-run"
    ]
  }
});

client.on("qr", async qr => {
  isReady = false;
  latestQr = qr;
  latestQrAt = new Date();
  try {
    latestQrDataUrl = await qrcode.toDataURL(qr, { margin: 1, width: 280 });
  } catch (error) {
    latestQrDataUrl = "";
    console.error("Failed to generate QR data URL:", error);
  }
  console.log("Scan this QR using WhatsApp -> Settings -> Linked devices -> Link a device:");
  qrcodeTerminal.generate(qr, { small: true });
});

client.on("authenticated", () => {
  console.log("WhatsApp authenticated.");
});

client.on("ready", () => {
  isReady = true;
  latestQr = "";
  latestQrDataUrl = "";
  latestQrAt = null;
  console.log("WhatsApp relay ready.");
});

client.on("auth_failure", msg => {
  isReady = false;
  console.error("WhatsApp authentication failed:", msg);
});

client.on("disconnected", reason => {
  isReady = false;
  console.error("WhatsApp disconnected:", reason);
});

process.on("unhandledRejection", error => {
  console.error("Unhandled rejection:", error);
});

process.on("uncaughtException", error => {
  console.error("Uncaught exception:", error);
});

client.initialize().catch(error => {
  console.error("Client initialize failed:", error);
});

function checkToken(req, res) {
  if (!TOKEN) return true;
  const auth = req.headers.authorization || "";
  if (auth === `Bearer ${TOKEN}`) return true;
  res.status(401).json({ ok: false, error: "Unauthorized" });
  return false;
}

app.get("/healthz", (req, res) => {
  res.json({ ok: true, ready: isReady });
});

app.get("/qr", (req, res) => {
  if (!checkToken(req, res)) return;
  if (isReady) return res.json({ ok: true, ready: true, message: "WhatsApp relay is already ready." });
  if (!latestQrDataUrl) {
    return res.status(404).json({
      ok: false,
      ready: false,
      error: "QR is not available yet. Restart the relay or wait for WhatsApp Web to request a new QR."
    });
  }
  const ageSeconds = latestQrAt ? Math.max(0, Math.round((Date.now() - latestQrAt.getTime()) / 1000)) : null;
  res.json({
    ok: true,
    ready: false,
    qr: latestQr,
    qr_data_url: latestQrDataUrl,
    age_seconds: ageSeconds
  });
});

app.get("/groups", async (req, res) => {
  if (!checkToken(req, res)) return;
  if (!isReady) return res.status(503).json({ ok: false, error: "WhatsApp client not ready" });

  try {
    const chats = await client.getChats();
    const groups = chats
      .filter(c => c.isGroup)
      .map(c => ({ name: c.name, id: c.id._serialized }));
    res.json({ ok: true, groups });
  } catch (error) {
    console.error("Failed to load groups:", error);
    res.status(500).json({ ok: false, error: "Failed to load groups" });
  }
});

app.post("/send", async (req, res) => {
  if (!checkToken(req, res)) return;
  if (!isReady) return res.status(503).json({ ok: false, error: "WhatsApp client not ready" });

  const groupId = req.body.group_id || DEFAULT_GROUP_ID;
  const message = req.body.text || req.body.message || "";

  if (!groupId) return res.status(400).json({ ok: false, error: "Missing group_id" });
  if (!message.trim()) return res.status(400).json({ ok: false, error: "Missing message" });

  try {
    await client.sendMessage(groupId, message);
    res.json({ ok: true });
  } catch (error) {
    console.error("Failed to send message:", error);
    res.status(500).json({ ok: false, error: "Failed to send message" });
  }
});

app.listen(PORT, "127.0.0.1", () => {
  console.log(`WhatsApp relay listening on http://127.0.0.1:${PORT}`);
});

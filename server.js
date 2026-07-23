import express from "express";
import qrcode from "qrcode-terminal";
import pino from "pino";

import {
    default as makeWASocket,
    DisconnectReason,
    useMultiFileAuthState
} from "@whiskeysockets/baileys";

const app = express();
app.use(express.json());

let sock;

async function connectWhatsapp() {

    const { state, saveCreds } =
        await useMultiFileAuthState("auth");

    sock = makeWASocket({
        auth: state,
        logger: pino({ level: "silent" })
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", ({ connection, qr, lastDisconnect }) => {

        if (qr) {
            console.clear();
            qrcode.generate(qr, { small: true });
            console.log("\nScan this QR using WhatsApp.");
        }

        if (connection === "open") {
            console.log("✅ WhatsApp Connected");
        }

        if (connection === "close") {

            const reconnect =
                lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;

            if (reconnect)
                connectWhatsapp();
        }

    });

}

await connectWhatsapp();

app.post("/send-message", async (req, res) => {

    try {

        const { phone, message } = req.body;

        const jid = phone + "@s.whatsapp.net";

        await sock.sendMessage(jid, {
            text: message
        });

        res.json({
            success: true
        });

    } catch (err) {

        res.status(500).json({
            success: false,
            error: err.message
        });

    }

});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`API running on port ${PORT}`);
});
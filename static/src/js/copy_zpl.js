/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

function copyToClipboard(text) {
    // Usa API moderna si está disponible
    if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text);
    }
    // Fallback para navegadores viejos
    return new Promise((resolve, reject) => {
        try {
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.style.position = "fixed";
            textarea.style.opacity = "0";
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            const successful = document.execCommand("copy");
            document.body.removeChild(textarea);
            if (successful) {
                resolve();
            } else {
                reject(new Error("execCommand('copy') failed"));
            }
        } catch (error) {
            reject(error);
        }
    });
}

// 👇 IMPORTANTE: registramos una FUNCIÓN, no un objeto
registry
    .category("actions")
    .add("remote_picking_zpl_copy_zpl", async function (env, action) {
        const text = (action.params && action.params.zpl_text) || "";
        if (!text) {
            env.services.notification.add(
                _t("No hay ZPL para copiar."),
                { type: "warning" }
            );
            return;
        }

        try {
            await copyToClipboard(text);
            env.services.notification.add(
                _t("Etiqueta ZPL copiada al portapapeles."),
                { type: "success" }
            );
        } catch (error) {
            console.error("Error copying ZPL to clipboard:", error);
            env.services.notification.add(
                _t("No se pudo copiar automáticamente. Copiá manualmente desde el formulario."),
                { type: "warning" }
            );
        }
    });

from odoo import api, fields, models, _


class RemotePickingLabel(models.Model):
    _name = "remote.picking.label"
    _description = "Etiqueta ZPL generada desde Odoo remoto"
    _order = "create_date desc"

    name = fields.Char("Descripción", compute="_compute_name", store=True)
    connection_id = fields.Many2one(
        "remote.odoo.connection",
        string="Conexión Odoo remoto",
        required=True,
        ondelete="cascade",
    )
    sale_order_name = fields.Char("Nota de venta")
    picking_name = fields.Char("Pedido / Transferencia")
    picking_id_remote = fields.Integer("ID picking remoto")
    product_name = fields.Char("Producto")
    product_id_remote = fields.Integer("ID producto remoto")
    qty = fields.Float("Cantidad")
    zpl_text = fields.Text("Etiqueta ZPL")
    printed = fields.Boolean("Impresa", default=False)
    state = fields.Selection(
        [
            ("nuevo", "Nuevo"),
            ("usado", "Usado"),
        ],
        string="Estado",
        default="nuevo",
    )

    @api.depends("sale_order_name", "picking_name", "product_name", "qty")
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.sale_order_name:
                parts.append(rec.sale_order_name)
            if rec.picking_name:
                parts.append(rec.picking_name)
            if rec.product_name:
                parts.append(rec.product_name)
            if rec.qty:
                parts.append("(%s)" % rec.qty)
            rec.name = " - ".join(parts) if parts else _("Etiqueta ZPL")

    def action_copy_notice(self):
        """Marcar como impresa y disparar copia al portapapeles vía client action JS."""
        self.ensure_one()
        self.write({"printed": True})

        return {
            "type": "ir.actions.client",
            "tag": "remote_picking_zpl_copy_zpl",
            "params": {
                "zpl_text": self.zpl_text or "",
            },
        }

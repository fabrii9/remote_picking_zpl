from odoo import api, fields, models, _
from odoo.exceptions import UserError
import xmlrpc.client
import ast


class RemoteOdooConnection(models.Model):
    _name = "remote.odoo.connection"
    _description = "Conexión a Odoo remoto"

    name = fields.Char("Nombre", required=True)
    active = fields.Boolean(default=True)

    remote_url = fields.Char(
        "URL base Odoo remoto",
        required=True,
        help="Ej: https://mi-servidor-odoo.com",
    )
    remote_db = fields.Char("Base de datos remota", required=True)
    remote_user = fields.Char("Usuario", required=True)
    remote_password = fields.Char("Contraseña", required=True)

    picking_domain = fields.Text(
        "Dominio de búsqueda de transferencias",
        help=(
            "Dominio en formato Python para buscar stock.picking en Odoo remoto.\n"
            "Ejemplo: [('state', '=', 'assigned'), ('picking_type_code', '=', 'outgoing')]\n"
            "Si se deja vacío, se usará un dominio por defecto."
        ),
    )

    allowed_categ_ids = fields.Text(
        "Categorías de producto permitidas (IDs remotos)",
        help=(
            "IDs de product.category del Odoo remoto, separados por coma.\n"
            "Ejemplo: 3,7,15\n"
            "Si se deja vacío, no se filtran productos por categoría."
        ),
    )

    # ===========================================================
    # PLANTILLA ZPL ACTUALIZADA (Pedido + Transferencia separadas)
    # ===========================================================
    def _default_zpl_template(self):
        """Plantilla ZPL por defecto usando placeholders de Python."""
        return (
            "^XA\n"
            "^CF0,30\n"
            "^FO50,40^FD Pedido: {sale_order_name} ^FS\n"
            "^FO50,80^FD Transferencia: {picking_name} ^FS\n"
            "^FO50,120^FD Producto: {product_name} ^FS\n"
            "^FO50,160^FD Cantidad: {qty} ^FS\n"
            "^XZ"
        )

    zpl_template = fields.Text(
        "Plantilla ZPL",
        help=(
            "Plantilla ZPL para cada etiqueta. Usa placeholders Python:\n"
            "{picking_name}, {product_name}, {qty}, {sale_order_name}.\n\n"
            "Ejemplo:\n"
            "^XA\n"
            "^CF0,30\n"
            "^FO50,40^FD Pedido: {sale_order_name} ^FS\n"
            "^FO50,80^FD Transferencia: {picking_name} ^FS\n"
            "^FO50,120^FD Producto: {product_name} ^FS\n"
            "^FO50,160^FD Cantidad: {qty} ^FS\n"
            "^XZ"
        ),
        default=_default_zpl_template,
    )

    label_ids = fields.One2many(
        "remote.picking.label",
        "connection_id",
        string="Etiquetas generadas",
    )

    # ===========================================================
    # Helpers
    # ===========================================================

    def _get_domain(self):
        self.ensure_one()
        if self.picking_domain:
            try:
                domain = ast.literal_eval(self.picking_domain)
                if not isinstance(domain, (list, tuple)):
                    raise ValueError("El dominio debe ser una lista o tupla.")
                return domain
            except Exception as e:
                raise UserError(_("Error al interpretar el dominio: %s") % e)
        return [("state", "=", "assigned")]

    def _parse_allowed_categ_ids(self):
        self.ensure_one()
        if not self.allowed_categ_ids:
            return set()
        ids = set()
        for part in self.allowed_categ_ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.add(int(part))
            except ValueError:
                raise UserError(
                    _("El valor '%s' en Categorías permitidas no es un entero válido.")
                    % part
                )
        return ids

    def _get_xmlrpc_proxies(self):
        self.ensure_one()
        if not self.remote_url:
            raise UserError(_("Falta la URL del Odoo remoto."))

        url = self.remote_url.rstrip("/")
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        models_proxy = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        return common, models_proxy

    # ===========================================================
    # Conexión y pruebas
    # ===========================================================

    def test_connection(self):
        for rec in self:
            common, _models = rec._get_xmlrpc_proxies()
            try:
                uid = common.authenticate(
                    rec.remote_db, rec.remote_user, rec.remote_password, {}
                )
            except Exception as e:
                raise UserError(_("Error conectando al Odoo remoto: %s") % e)

            if not uid:
                raise UserError(_("No se pudo autenticar con las credenciales dadas."))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Conexión exitosa"),
                "message": _("Conexión al Odoo remoto verificada correctamente."),
                "type": "success",
                "sticky": False,
            },
        }

    # ===========================================================
    # GENERACIÓN DE ETIQUETAS
    # ===========================================================

    def _generate_labels(self):
        self.ensure_one()

        common, models_proxy = self._get_xmlrpc_proxies()
        try:
            uid = common.authenticate(
                self.remote_db, self.remote_user, self.remote_password, {}
            )
        except Exception as e:
            raise UserError(_("Error conectando al Odoo remoto: %s") % e)

        if not uid:
            raise UserError(_("No se pudo autenticar en el Odoo remoto."))

        domain = self._get_domain()

        # Buscar pickings
        try:
            picking_ids = models_proxy.execute_kw(
                self.remote_db,
                uid,
                self.remote_password,
                "stock.picking",
                "search",
                [domain],
            )
        except Exception as e:
            raise UserError(_("Error buscando transferencias remotas: %s") % e)

        Label = self.env["remote.picking.label"]
        Label.search([("connection_id", "=", self.id)]).unlink()

        if not picking_ids:
            return 0

        # Leer pickings
        try:
            pickings = models_proxy.execute_kw(
                self.remote_db,
                uid,
                self.remote_password,
                "stock.picking",
                "read",
                [picking_ids],
                {"fields": ["name", "origin"]},
            )
        except Exception as e:
            raise UserError(_("Error leyendo transferencias remotas: %s") % e)

        picking_by_id = {p["id"]: p for p in pickings}

        # Leer movimientos
        try:
            moves = models_proxy.execute_kw(
                self.remote_db,
                uid,
                self.remote_password,
                "stock.move",
                "search_read",
                [[("picking_id", "in", picking_ids)]],
                {"fields": ["picking_id", "product_id", "product_uom_qty", "name"]},
            )
        except Exception as e:
            raise UserError(_("Error leyendo movimientos remotos: %s") % e)

        if not moves:
            return 0

        # Leer categorías de productos
        product_ids = list(
            {
                mv["product_id"][0]
                for mv in moves
                if mv.get("product_id")
                and isinstance(mv["product_id"], (list, tuple))
            }
        )

        product_categ_by_id = {}
        if product_ids:
            prod_records = models_proxy.execute_kw(
                self.remote_db,
                uid,
                self.remote_password,
                "product.product",
                "read",
                [product_ids],
                {"fields": ["categ_id"]},
            )
            for prod in prod_records:
                categ = prod.get("categ_id") or False
                categ_id = (
                    categ[0] if isinstance(categ, (list, tuple)) and categ else False
                )
                product_categ_by_id[prod["id"]] = categ_id

        allowed_categ_ids = self._parse_allowed_categ_ids()
        template = self.zpl_template or self._default_zpl_template()
        created = 0

        # Crear etiquetas
        for move in moves:
            picking_id = move["picking_id"][0]
            picking_info = picking_by_id.get(picking_id, {}) or {}

            picking_name = picking_info.get("name", "N/A")
            sale_order_name = picking_info.get("origin") or ""

            product_field = move.get("product_id") or [False, "Producto sin nombre"]
            if isinstance(product_field, (list, tuple)):
                product_id_remote = product_field[0]
                product_name = product_field[1]
            else:
                product_id_remote = 0
                product_name = str(product_field)

            if allowed_categ_ids:
                categ_id = product_categ_by_id.get(product_id_remote)
                if not categ_id or categ_id not in allowed_categ_ids:
                    continue

            qty = move.get("product_uom_qty") or 0.0

            try:
                zpl_label = template.format(
                    picking_name=picking_name,
                    product_name=product_name,
                    qty=qty,
                    sale_order_name=sale_order_name,
                )
            except Exception as e:
                raise UserError(
                    _(
                        "Error al formatear la plantilla ZPL. Revisá los placeholders.\nDetalle: %s"
                    )
                    % e
                )

            self.env["remote.picking.label"].create(
                {
                    "connection_id": self.id,
                    "sale_order_name": sale_order_name,
                    "picking_name": picking_name,
                    "picking_id_remote": picking_id,
                    "product_name": product_name,
                    "product_id_remote": product_id_remote,
                    "qty": qty,
                    "zpl_text": zpl_label,
                }
            )
            created += 1

        return created

    # ===========================================================
    # Acción servidor: generar + abrir vista
    # ===========================================================

    @api.model
    def _generate_labels_and_get_action(self):
        conn = None
        ctx = self.env.context

        if ctx.get("active_model") == "remote.odoo.connection" and ctx.get("active_id"):
            conn = self.browse(ctx["active_id"])

        if not conn:
            conn = self.search([("active", "=", True)], limit=1)

        if not conn:
            raise UserError(
                _(
                    "No hay ninguna conexión activa configurada.\n"
                    "Creá al menos una en 'Conexiones'."
                )
            )

        conn._generate_labels()

        action = self.env.ref("remote_picking_zpl.action_remote_picking_label").read()[0]
        action["domain"] = [("connection_id", "=", conn.id)]
        return action

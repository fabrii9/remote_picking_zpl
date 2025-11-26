{
    "name": "Remote Picking ZPL Labels",
    "version": "16.0.6.0.0",
    "summary": "Conecta a un Odoo remoto y genera etiquetas ZPL dinámicas por producto en transferencias",
    "author": "Fabrizio + ChatGPT",
    "website": "",
    "category": "Inventory",
    "license": "LGPL-3",
    "depends": ["stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/remote_odoo_config_views.xml",
        "views/remote_picking_label_views.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "remote_picking_zpl/static/src/js/copy_zpl.js"
        ]
    },
    "installable": True,
    "application": True
}

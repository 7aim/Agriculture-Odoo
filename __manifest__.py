{
    'name': "Kənd Təsərrüfatı İdarəetməsi",

    'author': "Aim",
    'website': "https://www.github.com/7aim/Agriculture-Odoo",
    'category': 'Industries',
    'version': '18.0.2.0.0',
    'depends': ['base', 'stock', 'purchase'],  
    'data': [
        'security/ir.model.access.csv',
        'data/operation_types.xml',
        'wizard/bulk_row_creator_views.xml',
        'views/agriculture_operation_views.xml',
        'views/agriculture_worker_views.xml',
        'views/agriculture_pivot_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True, 
    'license': 'LGPL-3',
}
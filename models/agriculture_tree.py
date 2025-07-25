from odoo import models, fields, api

# Ağac
class AgricultureTree(models.Model):
    _name = 'agriculture.tree'
    _description = 'Təsərrüfat Ağacı'

    name = fields.Char(string="Ağac Kodu", required=True, copy=False, readonly=True, default=lambda self: 'Yeni')
    row_id = fields.Many2one('agriculture.row', string="Aid Olduğu Cərgə", required=True, ondelete='cascade')
    plot_id = fields.Many2one('agriculture.plot', string="Aid Olduğu Sahə", related='row_id.plot_id', store=True, readonly=True)
    
    # Ağac növü məhsul kateqoriyasından seçilir
    product_id = fields.Many2one('product.template', string="Ağac Növü", 
        domain="[('categ_id.name', 'ilike', 'mehsul')]")
    
    plant_date = fields.Date(string="Əkilmə Tarixi")
    state = fields.Selection([
        ('young', 'Cavan'),
        ('productive', 'Məhsuldar'),
        ('sick', 'Xəstə'),
        ('removed', 'Çıxarılıb')
    ], string="Vəziyyəti", default='young')

    # Ağac nömrəsi
    @api.model_create_multi
    def create(self, vals_list):
        # Cərgə üzrə ağac sayını hesablayırıq
        row_counters = {}
        
        for vals in vals_list:
            if vals.get('name', 'Yeni') == 'Yeni':
                row_id = vals.get('row_id')
                if row_id:
                    row = self.env['agriculture.row'].browse(row_id)
                    if row:
                        # Bu cərgə üçün counter varsa istifadə et, yoxsa başla
                        if row_id not in row_counters:
                            # Bu cərgədə neçə ağac var?
                            existing_count = self.search_count([('row_id', '=', row_id)])
                            row_counters[row_id] = existing_count
                        
                        # Counter artır və ağac kodu yarat
                        row_counters[row_id] += 1
                        vals['name'] = f"{row.name} A{row_counters[row_id]}"
                    else:
                        vals['name'] = self.env['ir.sequence'].next_by_code('agriculture.tree') or 'Yeni'
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('agriculture.tree') or 'Yeni'
        return super().create(vals_list)
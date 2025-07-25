from odoo import models, fields, api

class AgricultureOperationType(models.Model):
    _name = 'agriculture.operation.type'
    _description = 'Kənd Təsərrüfatı Əməliyyat Növü'

    name = fields.Char(string="Əməliyyatın Adı", required=True)
    category = fields.Selection([
        ('nutrition', 'Qidalandırma (Gübrələmə)'),
        ('irrigation', 'Suvarma'),
        ('treatment', 'Müalicə/Dərmanlanma'),
        ('maintenance', 'Baxım'),
        ('harvesting', 'Məhsul Yığımı'),
        ('planting', 'Əkmə/Tikinti'),
        ('other', 'Digər')
    ], string="Kateqoriya", required=True, default='other')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Bu adda əməliyyat növü artıq mövcuddur!")
    ]


class AgricultureOperation(models.Model):
    _name = 'agriculture.operation'
    _description = 'Kənd Təsərrüfatı Əməliyyatı'
    _order = 'date desc, id desc'

    name = fields.Char(string="Əməliyyat", compute='_compute_name', store=True)
    operation_type_id = fields.Many2one('agriculture.operation.type', string="Əməliyyat Növü", required=True)
    operation_category = fields.Selection(string="Əməliyyat Kateqoriyası", related='operation_type_id.category', store=True)
    date = fields.Datetime(string="Tarix və Vaxt", required=True, default=fields.Datetime.now)
    state = fields.Selection([
        ('draft', 'Qaralama'),
        ('done', 'İcra Edildi'),
        ('cancelled', 'Ləğv Edildi')
    ], string="Status", default='draft', required=True)

    plot_id = fields.Many2one('agriculture.plot', string="Sahə")
    row_ids = fields.Many2many('agriculture.row', string="Cərgələr", domain="[('plot_id', '=', plot_id)]")
    
    # İşçi məlumatları
    worker_ids = fields.Many2many('agriculture.worker', string="İşçilər", domain="[('state', '=', 'active')]")
    worker_cost = fields.Monetary(string="İşçi Xərcləri", currency_field='currency_id', help="Bu əməliyyat üçün işçilərə verilən ümumi məbləğ")
    worker_payment_ids = fields.One2many('agriculture.worker.payment', 'operation_id', string="İşçi Ödənişləri")

    # Ağac sayı və ağac başına hesablamalar
    total_trees = fields.Integer(string="Ümumi Ağac Sayı", compute='_compute_tree_stats', store=True)

    notes = fields.Text(string="Qeydlər")

    product_line_ids = fields.One2many('agriculture.operation.line', 'operation_id', string="Məhsul Xərcləri")
    total_cost = fields.Monetary(string="Ümumi Xərc", compute='_compute_total_cost', store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string="Valyuta", default=lambda self: self.env.company.currency_id)

    @api.model
    def create(self, vals):
        """Yeni əməliyyat yaradılanda"""
        operation = super().create(vals)
        
        # Worker cost daxil edilibsə və işçilər seçilibsə, payment yarat
        if operation.worker_cost and operation.worker_cost > 0 and operation.worker_ids:
            operation._create_worker_expenses()
            
        return operation

    @api.depends('row_ids', 'product_line_ids.product_qty', 'product_line_ids.product_id')
    def _compute_tree_stats(self):
        for operation in self:
            # Seçilmiş cərgələrdəki ümumi ağac sayı
            total_trees = sum(row.tree_count for row in operation.row_ids)
            operation.total_trees = total_trees

    @api.onchange('operation_type_id')
    def _onchange_operation_type_id(self):
        """Əməliyyat növü dəyişəndə məhsul xətlərini təmizlə və məhsul domain-ni yenilə"""
        if self.operation_type_id:
            # Mövcud məhsul xətlərini təmizlə
            self.product_line_ids = [(5, 0, 0)]

    @api.depends('operation_type_id', 'date')
    def _compute_name(self):
        for rec in self:
            if rec.operation_type_id and rec.date:
                rec.name = f"{rec.operation_type_id.name} - {rec.date.strftime('%Y-%m-%d %H:%M')}"
            else:
                rec.name = "Yeni Əməliyyat"

    @api.depends('product_line_ids.cost', 'worker_cost')
    def _compute_total_cost(self):
        """Ümumi xərci hesabla"""
        for operation in self:
            product_cost = sum(line.cost for line in operation.product_line_ids)
            operation.total_cost = product_cost + operation.worker_cost

    def action_done(self):
        """Əməliyyatı tamamla və məhsul miqdarlarını azalt"""
        for operation in self:
            # Məhsulları birbaşa anbardan azalt
            for line in operation.product_line_ids:
                if line.product_id and line.product_qty > 0:
                    # Məhsulun mövcud miqdarını yoxla
                    current_qty = line.product_id.qty_available
                    
                    if current_qty >= line.product_qty:
                        # Tam miqdarı azalt
                        operation._reduce_product_qty(line.product_id, line.product_qty)
                    elif current_qty > 0:
                        # Mövcud olanı azalt
                        operation._reduce_product_qty(line.product_id, current_qty)
            
            # İşçi xərclərini işçi hesabatına əlavə et
            operation._create_worker_expenses()
        
        # Status-u done et
        self.write({'state': 'done'})
        return True
        
    def _reduce_product_qty(self, product, qty):
        """Məhsul miqdarını birbaşa azalt"""
        try:
            # Stock quant tapırıq və birbaşa azaldırıq
            quants = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('quantity', '>', 0),
                ('location_id.usage', '=', 'internal')
            ], order='quantity desc')
            
            remaining_qty = qty
            for quant in quants:
                if remaining_qty <= 0:
                    break
                    
                if quant.quantity >= remaining_qty:
                    # Bu quant-dan kifayət qədər azalt
                    quant.quantity -= remaining_qty
                    remaining_qty = 0
                else:
                    # Bu quant-ı tamamilə azalt
                    remaining_qty -= quant.quantity
                    quant.quantity = 0
                    
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Product quantity reduction error: {str(e)}")
    
    def _create_worker_expenses(self):
        """İşçi xərclərini işçi ödənişinə əlavə et"""
        if not self.worker_ids or not self.worker_cost or self.worker_cost <= 0:
            return
            
        # Hər işçi üçün ödəniş yaradırıq - siz yazdığınız məbləği işçilər arasında bölürük
        worker_count = len(self.worker_ids)
        cost_per_worker = self.worker_cost / worker_count
        
        for worker in self.worker_ids:
            # İşçi üçün payment yaradırıq  
            self.env['agriculture.worker.payment'].create({
                'worker_id': worker.id,
                'operation_id': self.id,  # Əməliyyat ID-ni əlavə edirik
                'date': self.date.date() if self.date else fields.Date.context_today(self),
                'amount': cost_per_worker,
                'description': f"{self.operation_type_id.name} əməliyyatı üçün iş haqqı (Əməliyyat: {self.name})",
                'payment_type': 'salary',
                'state': 'draft'  # İlk olaraq qaralama vəziyyətində
            })

    def write(self, vals):
        """Əməliyyat yenilənəndə"""
        # Köhnə məlumatları saxla
        old_data = {}
        for record in self:
            old_data[record.id] = {
                'worker_cost': record.worker_cost,
                'worker_ids': record.worker_ids.ids
            }
        
        res = super().write(vals)
        
        # Worker cost və ya işçilər dəyişibsə
        for record in self:
            old_record = old_data[record.id]
            cost_changed = 'worker_cost' in vals and record.worker_cost != old_record['worker_cost']
            workers_changed = 'worker_ids' in vals and record.worker_ids.ids != old_record['worker_ids']
            
            if cost_changed or workers_changed:
                # Köhnə payment-ləri sil (yalnız bu əməliyyat üçün yaradılmış)
                old_payments = self.env['agriculture.worker.payment'].search([
                    ('operation_id', '=', record.id)
                ])
                old_payments.unlink()
                
                # Yeni payment-lər yarat
                if record.worker_cost and record.worker_cost > 0 and record.worker_ids:
                    record._create_worker_expenses()
        
        return res
    
    def action_cancel(self):
        """Əməliyyatı ləğv et"""
        self.write({'state': 'cancelled'})
        
    def action_draft(self):
        """Əməliyyatı qaralama vəziyyətinə qaytar"""
        self.write({'state': 'draft'})
        
    """
    def action_create_purchase_order(self):
        purchase_lines = []
        
        for line in self.product_line_ids:
            if line.product_qty > line.available_qty:
                # Çatışmayan miqdar
                shortage = line.product_qty - line.available_qty
                
                # Supplier məlumatlarını tapırıq
                supplier_info = line.product_id.seller_ids[:1] if line.product_id.seller_ids else False
                
                # Purchase Order Line yaradırıq
                purchase_line_vals = {
                    'product_id': line.product_id.id,
                    'product_qty': shortage,
                    'product_uom': line.product_id.uom_po_id.id or line.product_id.uom_id.id,
                    'price_unit': supplier_info.price if supplier_info else line.product_id.standard_price,
                    'name': line.product_id.display_name,
                    'date_planned': fields.Datetime.now(),
                }
                purchase_lines.append((0, 0, purchase_line_vals))
        
        if purchase_lines:
            # İlk supplier-ı tapırıq
            first_product = self.product_line_ids[0].product_id if self.product_line_ids else False
            partner_id = False
            
            if first_product and first_product.seller_ids:
                partner_id = first_product.seller_ids[0].partner_id.id
            
            # Purchase Order yaradırıq
            purchase_vals = {
                'origin': self.name,
                'order_line': purchase_lines,
                'date_order': fields.Datetime.now(),
            }
            
            if partner_id:
                purchase_vals['partner_id'] = partner_id
                
            purchase_order = self.env['purchase.order'].create(purchase_vals)
            
            # Purchase Order-i göstəririk
            return {
                'type': 'ir.actions.act_window',
                'name': 'Yaradılmış Sifariş',
                'res_model': 'purchase.order',
                'res_id': purchase_order.id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            # Heç nə lazım deyil
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Məlumat',
                    'message': 'Bütün məhsullar anbarda mövcuddur.',
                    'type': 'info',
                }
            }
    """

class AgricultureOperationLine(models.Model):
    _name = 'agriculture.operation.line'
    _description = 'Kənd Təsərrüfatı Əməliyyatı Məhsul Sətiri'

    operation_id = fields.Many2one('agriculture.operation', string="Əməliyyat", ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string="Məhsul", required=True, domain="[('type', '=', 'consu')]")
    product_qty = fields.Float(string="Miqdar", required=True, default=1.0)
    product_uom_id = fields.Many2one('uom.uom', string="Ölçü Vahidi", related='product_id.uom_id')
    available_qty = fields.Float(string="Anbardan Mövcud", compute='_compute_available_qty', store=False, readonly=True)
    
    unit_cost = fields.Float(string="Vahidin Qiyməti", related='product_id.standard_price')
    cost = fields.Monetary(string="Xərc", compute='_compute_cost', store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='operation_id.currency_id')

    @api.depends('product_id')
    def _compute_available_qty(self):
        for line in self:
            if line.product_id:
                try:
                    line.available_qty = line.product_id.qty_available
                except:
                    # Əgər xəta varsa 0 ver
                    line.available_qty = 0.0
            else:
                line.available_qty = 0.0

    @api.depends('product_qty', 'unit_cost')
    def _compute_cost(self):
        for line in self:
            line.cost = line.product_qty * line.unit_cost
            
    @api.onchange('product_qty', 'product_id')
    def _onchange_product_qty(self):
        """Məhsul miqdarı dəyişəndə xəbərdarlıq ver"""
        if self.product_id and self.product_qty > self.available_qty:
            return {
                'warning': {
                    'title': 'Diqqət!',
                    'message': f'Seçdiyiniz miqdar ({self.product_qty}) anbarda mövcud miqdardan ({self.available_qty}) çoxdur. '
                              f'Əməliyyatı tamamlamaq üçün əlavə məhsul sifariş etməli olacaqsınız.'
                }
            }
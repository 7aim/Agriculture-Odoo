from odoo import models, fields, api

# Kənd Təsərrüfatı İşçisi
class AgricultureWorker(models.Model):
    _name = 'agriculture.worker'
    _description = 'Kənd Təsərrüfatı İşçisi'
    _order = 'name'
    
    # Silinməni tamamilə qadağan et
    _auto_archive = False

    name = fields.Char(string="İşçi Adı", required=True)
    phone = fields.Char(string="Telefon")
    currency_id = fields.Many2one('res.currency', string="Valyuta", default=lambda self: self.env.company.currency_id)
    
    # Başlanğıc və bitiş tarixləri
    start_date = fields.Date(string="İşə Başlama Tarixi", default=fields.Date.context_today)
    end_date = fields.Date(string="İşdən Çıxma Tarixi")
    
    # Active sahəsini tamamilə silək
    state = fields.Selection([
        ('active', 'Aktiv'),
        ('terminated', 'İşdən Çıxarılmış'),
    ], string="Status", default='active', required=True)
    
    # Hesabat sahələri
    total_operations = fields.Integer(string="Ümumi Əməliyyat Sayı", compute='_compute_stats', store=False)
    total_payments = fields.Monetary(string="Ödənilmiş Məbləğ", compute='_compute_stats', store=False, currency_field='currency_id')

    # Qeydlər
    notes = fields.Text(string="Qeydlər")

    @api.depends('name')
    def _compute_stats(self):
        """İşçi statistikalarını hesabla"""
        for worker in self:
            # Əməliyyat sayı - işçinin iştirak etdiyi tamamlanmış əməliyyatlar
            operations = self.env['agriculture.operation'].search([('worker_ids', 'in', worker.id), ('state', '=', 'done')])
            worker.total_operations = len(operations)
            
            # Ödənilmiş məbləğ hesablama:
            total_amount = 0
            
            # 1. Əməliyyatlardan gələn məbləğlər
            for operation in operations:
                # Əvvəlcə bu əməliyyat üçün payment olub-olmadığını yoxla
                existing_payment = self.env['agriculture.worker.payment'].search([
                    ('worker_id', '=', worker.id),
                    ('operation_id', '=', operation.id),
                    ('state', '=', 'paid')
                ], limit=1)
                
                if existing_payment:
                    # Payment varsa onu hesabla
                    total_amount += existing_payment.amount
                elif operation.worker_cost and operation.worker_cost > 0:
                    # Payment yoxdursa worker_cost-u işçilər arasında böl
                    worker_count = len(operation.worker_ids)
                    if worker_count > 0:
                        total_amount += operation.worker_cost / worker_count
            
            # 2. Əməliyyatla əlaqəsi olmayan digər ödənişlər (maaş, bonus və s.)
            other_payments = self.env['agriculture.worker.payment'].search([
                ('worker_id', '=', worker.id),
                ('operation_id', '=', False),  # Əməliyyatla əlaqəsi yoxdur
                ('state', '=', 'paid')
            ])
            total_amount += sum(payment.amount for payment in other_payments)
            
            worker.total_payments = total_amount

    def action_view_operations(self):
        """İşçinin əməliyyatlarını göstər"""
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - Əməliyyatlar',
            'res_model': 'agriculture.operation',
            'view_mode': 'list,form',
            'domain': [('worker_ids', 'in', self.id)],
            'context': {'default_worker_ids': [(6, 0, [self.id])]},
        }

    def action_view_payments(self):
        """İşçinin ödənişlərini göstər"""
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - Ödənişlər',
            'res_model': 'agriculture.worker.payment',
            'view_mode': 'list,form',
            'domain': [('worker_id', '=', self.id)],
            'context': {'default_worker_id': self.id},
        }

    def action_terminate_worker(self):
        """İşçini işdən çıxar"""
        self.ensure_one()
        if self.state == 'active':
            self.write({
                'state': 'terminated',
                'end_date': fields.Date.context_today(self)
            })
        return True
        
    def action_reactivate_worker(self):
        """İşçini yenidən aktiv et"""
        self.ensure_one()
        if self.state == 'terminated':
            self.write({
                'state': 'active',
                'end_date': False
            })
        return True
    
    def unlink(self):
        """İşçi silinməsini tamamilə qadağan et"""
        raise models.UserError("İşçilər silinə bilməz! Əgər işçini işdən çıxarmaq istəyirsinizsə, 'İşdən Çıxar' düyməsini istifadə edin.")


class AgricultureWorkerPayment(models.Model):
    _name = 'agriculture.worker.payment'
    _description = 'İşçi Ödənişi'
    _order = 'date desc, id desc'

    name = fields.Char(string="Ödəniş", compute='_compute_name', store=True)
    worker_id = fields.Many2one('agriculture.worker', string="İşçi", required=True, ondelete='cascade', domain="[('state', '=', 'active')]")
    operation_id = fields.Many2one('agriculture.operation', string="Əməliyyat", ondelete='set null', help="Bu ödəniş hansı əməliyyat üçün")
    date = fields.Date(string="Ödəniş Tarixi", required=True, default=fields.Date.context_today)
    amount = fields.Monetary(string="Məbləğ", required=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string="Valyuta", default=lambda self: self.env.company.currency_id)
    
    payment_type = fields.Selection([
        ('salary', 'Maaş'),
        ('bonus', 'Bonus'),
        ('advance', 'Avans'),
        ('other', 'Digər')
    ], string="Ödəniş Növü", default='salary', required=True)
    
    description = fields.Text(string="Açıqlama")
    
    # Status
    state = fields.Selection([
        ('draft', 'Qaralama'),
        ('paid', 'Ödənilmiş'),
        ('cancelled', 'Ləğv edilmiş')
    ], string="Status", default='draft', required=True)

    @api.depends('worker_id', 'date', 'amount', 'operation_id')
    def _compute_name(self):
        for payment in self:
            if payment.worker_id and payment.date:
                operation_part = f" ({payment.operation_id.name})" if payment.operation_id else ""
                payment.name = f"{payment.worker_id.name} - {payment.date.strftime('%Y-%m-%d')} - {payment.amount} AZN{operation_part}"
            else:
                payment.name = "Yeni Ödəniş"

    def action_confirm_payment(self):
        """Ödənişi təsdiqlə"""
        self.write({'state': 'paid'})

    def action_cancel_payment(self):
        """Ödənişi ləğv et"""
        self.write({'state': 'cancelled'})

    def action_draft_payment(self):
        """Ödənişi qaralama vəziyyətinə qaytar"""
        self.write({'state': 'draft'})
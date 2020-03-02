# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools
from docutils.nodes import field
import datetime

class WizardInvoiceSaleCommission(models.Model):
    _name = 'wizard.invoice.sale.commission'

    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date('End Date', required=True)
    salesperson = fields.Many2one('res.users','Sales Person', required=True)
    
    @api.multi
    def print_commission_report(self):
        temp = []
        sale_invoice_commission_ids = self.env['invoice.sale.commission'].search([('date','>=',self.start_date),('date','<=',self.end_date),('user_id','=',self.salesperson.id)])
        if not sale_invoice_commission_ids:
            raise Warning('There Is No Any Commissions.')
        else:
            for a in sale_invoice_commission_ids:
                temp.append(a.id)
        data = temp
        datas = {
            'ids': self._ids,
            'model': 'invoice.sale.commission',
            'form': data,
            'start_date':self.start_date,
            'end_date':self.end_date,
            'user':self.salesperson.name
        }
#         return  self.env['report'].get_action(self, 'sales_commission_generic.sale_inv_comm_template', data=datas)
        return self.env.ref('sales_commission_generic.report_pdf').report_action(self,data=datas)




'''New class to handle sales commission in invoice.'''
class InvoiceSaleCommission(models.Model):
    _name = 'invoice.sale.commission'

    name = fields.Char(string="Description", size=512)
    type_name = fields.Char(string="Commission Name")
    comm_type = fields.Selection([
        ('standard', 'Standard'),
        ('partner', 'Partner Based'),
        ('mix', 'Product/Category/Margin Based'),
        ('margin', 'Commission based on Margin Amount'),
        ], 'Commission Type', copy=False, help="Select the type of commission you want to apply.")
    user_id = fields.Many2one('res.users', string='Sales Person',
                                 help="sales person associated with this type of commission",
                                 required=True)
    commission_amount = fields.Float(string="Commission Amount")
    invoice_id = fields.Many2one('account.invoice', string='Invoice Reference',
                                 help="Affected Invoice")
    order_id = fields.Many2one('sale.order', string='Order Reference',
                                 help="Affected Sale Order")
    commission_id = fields.Many2one('sale.commission', string='Sale Commission',
                                 help="Related Commission",)
    product_id = fields.Many2one('product.product', string='Product',
                                 help="product",)
    partner_id = fields.Many2one('res.partner', string='Partner')
    partner_type = fields.Selection([('Affiliated Partner', 'Affiliated Partner'),
                                      ('Non-Affiliated Partner', 'Non-Affiliated Partner')], string='Partner Type')
    categ_id = fields.Many2one('product.category', string='Product Category')
    sub_categ_id = fields.Many2one('product.category', string='Product Sub-Category')
    date = fields.Date('Date')
    invoiced = fields.Boolean(string='Invoiced', readonly=True, default=False)


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    commission_ids = fields.One2many('invoice.sale.commission', 'invoice_id', string='Sales Commissions',
                                     help="Sale Commission related to this invoice(based on sales person)")


    def get_standard_commission(self, commission_brw, invoice):
        '''This method calculates standard commission if any exception is not found for any product line.
           @return : Id of created commission record.'''
        invoice_commission_ids = []
        invoice_commission_obj = self.env['invoice.sale.commission']
        for line in invoice.invoice_line_ids:
            amount = line.price_subtotal
            standard_commission_amount = amount * (commission_brw.standard_commission / 100)
            name = 'Standard commission " '+ tools.ustr(commission_brw.name) +' ( ' + tools.ustr(commission_brw.standard_commission) + '%)" for product "' + tools.ustr(line.product_id.name) + '"'
            standard_invoice_commission_data = {
                               'name': name,
                               'user_id' : invoice.user_id.id,
                               'commission_id' : commission_brw.id,
                               'product_id' : line.product_id.id,
                               'type_name' : commission_brw.name,
                               'comm_type' : commission_brw.comm_type,
                               'commission_amount' : standard_commission_amount,
                               'invoice_id' : invoice.id,
                               'date':datetime.datetime.today()}
            invoice_commission_ids.append(invoice_commission_obj.create(standard_invoice_commission_data))
        return invoice_commission_ids

    def get_exceptions(self, line, commission_brw):
        '''This method searches exception for any product line.
           @return : List of ids for all exception for particular product line.'''
        exception_obj = self.env['sale.commission.exception']
        categ_obj = self.env['product.category']
        product_exception_id = exception_obj.search([
                                        ('product_id', '=', line.product_id.id),
                                        ('commission_id', '=', commission_brw.id),
                                        ('based_on', '=', 'Products')
                                        ])
        if product_exception_id:
            return product_exception_id
        subcateg_exception_id = exception_obj.search([
                                       ('sub_categ_id', '=', line.product_id.categ_id.id),
                                       ('commission_id', '=', commission_brw.id),
                                       ('based_on', '=', 'Product Sub-Categories')])
        if subcateg_exception_id:
            return subcateg_exception_id
        exclusive_categ_exception_id = exception_obj.search([
                                       ('categ_id', '=', line.product_id.categ_id.id),
                                       ('commission_id', '=', commission_brw.id),
                                       ('based_on', '=', 'Product Categories'),
                                       ])
        if exclusive_categ_exception_id:
            return exclusive_categ_exception_id
        affective_categ_ids = categ_obj.search([
                                        ('parent_left', '<', line.product_id.categ_id.parent_left),
                                        ('parent_right', '>', line.product_id.categ_id.parent_right)
                                        ])
        affective_categ_ids = [x.id for x in affective_categ_ids]
        categ_exception_id = exception_obj.search([
                                       ('categ_id', 'in', affective_categ_ids),
                                       ('commission_id', '=', commission_brw.id),
                                       ('based_on', '=', 'Product Categories'),
                                       ], order="order_category desc", limit=1)
        if categ_exception_id:
            return categ_exception_id
        return []

    def get_partner_commission(self, commission_brw, invoice):
        '''This method calculates commission for Partner Based.
           @return : List of ids for commission records created.'''
        invoice_commission_ids = []
        commission_precentage = commission_brw.standard_commission
        invoice_commission_obj = self.env['invoice.sale.commission']
        exception_obj = self.env['sale.commission.exception']
        sales_person_list = [x.id for x in commission_brw.user_ids]
        for line in invoice.invoice_line_ids:
            amount = line.price_subtotal
            invoice_commission_data = {}
            exception_ids = self.get_exceptions(line, commission_brw)
            margin = ((line.price_subtotal / line.quantity) - line.product_id.standard_price)
            actual_margin_percentage = (margin * 100) / line.product_id.standard_price
            if line.sol_id:
                margin = ((line.price_subtotal / line.quantity) - line.sol_id.purchase_price)
                actual_margin_percentage = (margin * 100) / line.sol_id.purchase_price
            if (invoice.user_id and invoice.user_id.id in sales_person_list) and invoice.partner_id.is_affiliated == True:
                commission_amount = amount * (commission_brw.affiliated_partner_commission / 100)
                name = 'Standard commission " '+ tools.ustr(commission_brw.name) +' (' + tools.ustr(commission_brw.affiliated_partner_commission) + '%)" for Affiliated Partner "' + tools.ustr(invoice.partner_id.name) + '"'
                invoice_commission_data = {'name' : name,
                                   'user_id' : invoice.user_id.id,
                                   'partner_id' : invoice.partner_id.id,
                                   'commission_id' : commission_brw.id,
                                   'type_name' : commission_brw.name,
                                   'comm_type' : commission_brw.comm_type,
                                   'partner_type' : 'Affiliated Partner',
                                   'commission_amount' : commission_amount,
                                   'invoice_id' : invoice.id,
                                   'date':datetime.datetime.today()}
            elif (invoice.user_id and invoice.user_id.id in sales_person_list) and  invoice.partner_id.is_affiliated == False:
                commission_amount = amount * (commission_brw.nonaffiliated_partner_commission / 100)
                name = 'Standard commission " '+ tools.ustr(commission_brw.name) +' (' + tools.ustr(commission_brw.nonaffiliated_partner_commission) + '%)" for Non-Affiliated Partner "' + tools.ustr(invoice.partner_id.name) + '"'
                invoice_commission_data = {'name' : name,
                                   'user_id' : invoice.user_id.id,
                                   'partner_id' : invoice.partner_id.id,
                                   'commission_id' : commission_brw.id,
                                   'type_name' : commission_brw.name,
                                   'comm_type' : commission_brw.comm_type,
                                   'partner_type' : 'Non-Affiliated Partner',
                                   'commission_amount' : commission_amount,
                                   'invoice_id' : invoice.id,
                                   'date':datetime.datetime.today()}
            if invoice_commission_data:
                    invoice_commission_ids.append(invoice_commission_obj.create(invoice_commission_data))
        return invoice_commission_ids

    
    #=================================================================================================================
    
    def get_margin_commission(self, commission_brw, invoice):
        '''This method calculates commission for Margin Based.
           @return : List of ids for commission records created.'''
        invoice_commission_ids = []
        commission_precentage = commission_brw.standard_commission
        invoice_commission_obj = self.env['invoice.sale.commission']
        exception_obj = self.env['sale.commission.exception']
        sales_person_list = [x.id for x in commission_brw.user_ids]
        for line in invoice.invoice_line_ids:
            
            amount = line.price_subtotal
            
            invoice_commission_data = {}
            exception_ids = self.get_exceptions(line, commission_brw)
            margin = ((line.price_subtotal / line.quantity) - line.product_id.standard_price)
            actual_margin_percentage = (margin * 100) / line.product_id.standard_price
            if line.sol_id:
                margin = ((line.price_subtotal / line.quantity) - line.sol_id.purchase_price)
                actual_margin_percentage = (margin * 100) / line.sol_id.purchase_price
            if (invoice.user_id and invoice.user_id.id in sales_person_list) and invoice.partner_id.is_affiliated == True:
                
                #commission_amount = amount * (commission_brw.affiliated_partner_commission / 100)
                
                margin = (line.price_unit - line.sol_id.purchase_price)*line.quantity
                
                commission_amount = margin * (commission_brw.margin_commission / 100)
                
                name = 'Margin commission " '+ tools.ustr(commission_brw.name) +' (' + tools.ustr(commission_brw.margin_commission) + '%)" for Affiliated Partner "' + tools.ustr(invoice.partner_id.name) + '"'
                invoice_commission_data = {'name' : name,
                                   'user_id' : invoice.user_id.id,
                                   'partner_id' : invoice.partner_id.id,
                                   'commission_id' : commission_brw.id,
                                   'type_name' : commission_brw.name,
                                   'comm_type' : commission_brw.comm_type,
                                   'partner_type' : 'Affiliated Partner',
                                   'commission_amount' : commission_amount,
                                   'invoice_id' : invoice.id,
                                   'date':datetime.datetime.today()}
            elif (invoice.user_id and invoice.user_id.id in sales_person_list) and  invoice.partner_id.is_affiliated == False:
                #commission_amount = amount * (commission_brw.nonaffiliated_partner_commission / 100)
                
                margin = (line.price_unit - line.sol_id.purchase_price)*line.quantity
                
                commission_amount = margin * (commission_brw.margin_commission / 100)
                
                
                name = 'Margin commission " '+ tools.ustr(commission_brw.name) +' (' + tools.ustr(commission_brw.margin_commission) + '%)" for Non-Affiliated Partner "' + tools.ustr(invoice.partner_id.name) + '"'
                invoice_commission_data = {'name' : name,
                                   'user_id' : invoice.user_id.id,
                                   'partner_id' : invoice.partner_id.id,
                                   'commission_id' : commission_brw.id,
                                   'type_name' : commission_brw.name,
                                   'comm_type' : commission_brw.comm_type,
                                   'partner_type' : 'Non-Affiliated Partner',
                                   'commission_amount' : commission_amount,
                                   'invoice_id' : invoice.id,
                                   'date':datetime.datetime.today()}
            if invoice_commission_data:
                    invoice_commission_ids.append(invoice_commission_obj.create(invoice_commission_data))
        return invoice_commission_ids
    
    #=================================================================================================================
    
    
    def get_mix_commission(self, commission_brw, invoice):
        '''This method calculates commission for Product/Category/Margin Based.
           @return : List of ids for commission records created.'''
        exception_obj = self.env['sale.commission.exception']
        invoice_commission_obj = self.env['invoice.sale.commission']
        invoice_commission_ids = []
        for line in invoice.invoice_line_ids:
            amount = line.price_subtotal
            invoice_commission_data = {}
            exception_ids = []
            if not line.product_id:continue
            margin = ((line.price_subtotal / line.quantity) - line.product_id.standard_price)
            actual_margin_percentage = (margin * 100) / line.product_id.standard_price
            if line.sol_id:
                margin = ((line.price_subtotal / line.quantity) - line.sol_id.purchase_price)
                actual_margin_percentage = (margin * 100) / line.sol_id.purchase_price
            exception_ids = self.get_exceptions(line, commission_brw)
            for exception in exception_ids:
                product_id = False
                categ_id = False
                sub_categ_id = False
                commission_precentage = commission_brw.standard_commission
                name = ''
                margin_percentage = exception.margin_percentage
                if exception.based_on_2 == 'Margin' and actual_margin_percentage > margin_percentage:
                    commission_precentage = exception.above_margin_commission
                elif exception.based_on_2 == 'Margin' and actual_margin_percentage <= margin_percentage:
                    commission_precentage = exception.below_margin_commission
                elif exception.based_on_2 == 'Commission Exception':
                    commission_precentage = exception.commission_precentage
                elif exception.based_on_2 == 'Fix Price' and line.price_unit >= exception.price :
                    commission_precentage = exception.price_percentage
                elif exception.based_on_2 == 'Fix Price' and line.price_unit < exception.price :
                    pass
                commission_amount = amount * (commission_precentage / 100)
                if exception.based_on == 'Products':
                    product_id = exception.product_id.id
                    name = 'Commission Exception for ' + tools.ustr(exception.based_on) + ' "' + tools.ustr(exception.product_id.name) + '" @' + tools.ustr(commission_precentage) + '%'
                elif exception.based_on == 'Product Categories':
                    categ_id = exception.categ_id.id
                    name = 'Commission Exception for ' + tools.ustr(exception.based_on) + ' "' + tools.ustr(exception.categ_id.name) + '" @' + tools.ustr(commission_precentage) + '%'
                elif exception.based_on == 'Product Sub-Categories':
                    sub_categ_id = exception.sub_categ_id.id
                    name = 'Commission Exception for ' + tools.ustr(exception.based_on) + ' "' + tools.ustr(exception.sub_categ_id.name) + '" @' + tools.ustr(commission_precentage) + '%'
                invoice_commission_data = {'name': name,
                                           'product_id': product_id or False,
                                           'commission_id' : commission_brw.id,
                                           'categ_id': categ_id or False,
                                           'sub_categ_id': sub_categ_id or False,
                                           'user_id' : invoice.user_id.id,
                                           'type_name' : commission_brw.name,
                                           'comm_type' : commission_brw.comm_type,
                                           'commission_amount' : commission_amount,
                                           'invoice_id' : invoice.id,
                                           'date':datetime.datetime.today()}
                invoice_commission_ids.append(invoice_commission_obj.create(invoice_commission_data))
        return invoice_commission_ids

    @api.multi
    def get_sales_commission(self):
        '''This is control method for calculating commissions(called from workflow).
           @return : List of ids for commission records created.'''
        for invoice in self:
            invoice_commission_ids = []
            if invoice.user_id and invoice.type == 'out_invoice':
                commission_obj = self.env['sale.commission']
                commission_id = commission_obj.search([('user_ids', 'in', invoice.user_id.id)])
                if not commission_id:return False
                else:
		                  commission_id = commission_id[0]
                commission_brw = commission_id
                
                if commission_brw.comm_type == 'mix':
                    invoice_commission_ids = self.get_mix_commission(commission_brw, invoice)
                elif commission_brw.comm_type == 'partner':
                    invoice_commission_ids = self.get_partner_commission(commission_brw, invoice)
                #=================================================================================
                elif commission_brw.comm_type == 'margin':
                    invoice_commission_ids = self.get_margin_commission(commission_brw, invoice)
                #=================================================================================
                
                else:
                    invoice_commission_ids = self.get_standard_commission(commission_brw, invoice)
        return invoice_commission_ids


    @api.multi
    def action_invoice_paid(self):
        res = super(AccountInvoice, self).action_invoice_paid()
        commission_configuration = self.env['res.config.settings'].search([], limit=1, order="id desc").commission_configuration
        if commission_configuration == 'payment':
            if self.state == 'paid':
                self.get_sales_commission()
        return res

    @api.multi
    def action_invoice_open(self):
        res = super(AccountInvoice, self).action_invoice_open()
        commission_configuration = self.env['res.config.settings'].search([], limit=1, order="id desc").commission_configuration
        if commission_configuration == 'invoice':
            self.get_sales_commission()
        return res

class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'


    sol_id = fields.Many2one('sale.order.line', string='Sales Order Line')
    

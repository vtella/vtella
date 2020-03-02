1. version 11.0.0.6
    
    a. Commission Calculation on margin amount functionality added. 
    b. Customization done in /sale/sale.py, /account/account_invoice.py, /commission_view.xml

2. version 11.0.0.7
    
    a. commission based upon invoice and payment option should calculate commssion upon orderline.price_unit - orderline.purchase_price.
       previously it was orderline.price_unit - orderline.product.standard_price

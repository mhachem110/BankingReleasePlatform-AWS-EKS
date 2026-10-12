CREATE TABLE banking_account.accounts (
    id varchar(64) PRIMARY KEY,
    customer_name varchar(100) NOT NULL,
    balance numeric(18,2) NOT NULL CHECK (balance >= 0),
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    active boolean NOT NULL
);
INSERT INTO banking_account.accounts VALUES
('ACC1001','Alex Example',1500.50,'USD',true),
('ACC1002','Sam Sample',75.00,'USD',true),
('ACC1003','Taylor Fiction',400.00,'USD',false),
('ACC1004','Jordan Demo',0.00,'USD',true);

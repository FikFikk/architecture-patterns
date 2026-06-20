"""
Bank Account dengan Event Sourcing

Contoh klasik event sourcing untuk bank account.
Mendemonstrasikan audit trail yang perfect untuk financial transactions.
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
from event_store import event_store, Event, ConcurrencyError


@dataclass
class Transaction:
    """Transaction detail"""
    transaction_id: str
    amount: float
    description: str
    timestamp: str


class BankAccountAggregate:
    """
    Bank Account Aggregate dengan Event Sourcing.
    
    Keuntungan untuk banking:
    - Perfect audit trail untuk compliance
    - Temporal queries (balance pada tanggal tertentu)
    - Dispute resolution dengan event replay
    - Fraud detection dari event patterns
    """
    
    def __init__(self, account_id: str):
        self.account_id = account_id
        self.owner_name: Optional[str] = None
        self.balance: float = 0.0
        self.is_active: bool = False
        self.transactions: List[Transaction] = []
        self.version: int = 0
    
    @classmethod
    def open_account(cls, account_id: str, owner_name: str, initial_deposit: float = 0.0) -> 'BankAccountAggregate':
        """
        Command: Open new bank account
        
        Business rules:
        - Initial deposit must be >= 0
        - Owner name required
        """
        if initial_deposit < 0:
            raise ValueError("Initial deposit cannot be negative")
        
        if not owner_name:
            raise ValueError("Owner name is required")
        
        account = cls(account_id)
        
        event_data = {
            "accountId": account_id,
            "ownerName": owner_name,
            "initialDeposit": initial_deposit,
            "openedAt": datetime.utcnow().isoformat()
        }
        
        event = event_store.append(
            aggregate_id=account_id,
            aggregate_type="BankAccount",
            event_type="AccountOpened",
            data=event_data,
            expected_version=0
        )
        
        account._apply_account_opened(event)
        
        return account
    
    def deposit(self, amount: float, description: str = "Deposit"):
        """
        Command: Deposit money
        
        Business rules:
        - Account must be active
        - Amount must be positive
        """
        if not self.is_active:
            raise ValueError("Account is not active")
        
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        
        transaction_id = f"txn_{datetime.utcnow().timestamp()}"
        
        event_data = {
            "accountId": self.account_id,
            "transactionId": transaction_id,
            "amount": amount,
            "description": description,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        event = event_store.append(
            aggregate_id=self.account_id,
            aggregate_type="BankAccount",
            event_type="MoneyDeposited",
            data=event_data,
            expected_version=self.version
        )
        
        self._apply_money_deposited(event)
    
    def withdraw(self, amount: float, description: str = "Withdrawal"):
        """
        Command: Withdraw money
        
        Business rules:
        - Account must be active
        - Amount must be positive
        - Sufficient balance (no overdraft)
        """
        if not self.is_active:
            raise ValueError("Account is not active")
        
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        
        if self.balance < amount:
            raise ValueError(f"Insufficient balance. Current: {self.balance}, Requested: {amount}")
        
        transaction_id = f"txn_{datetime.utcnow().timestamp()}"
        
        event_data = {
            "accountId": self.account_id,
            "transactionId": transaction_id,
            "amount": amount,
            "description": description,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        event = event_store.append(
            aggregate_id=self.account_id,
            aggregate_type="BankAccount",
            event_type="MoneyWithdrawn",
            data=event_data,
            expected_version=self.version
        )
        
        self._apply_money_withdrawn(event)
    
    def close_account(self, reason: str = "Customer request"):
        """
        Command: Close account
        
        Business rules:
        - Account must be active
        - Balance must be zero
        """
        if not self.is_active:
            raise ValueError("Account is already closed")
        
        if self.balance != 0:
            raise ValueError(f"Cannot close account with non-zero balance: {self.balance}")
        
        event_data = {
            "accountId": self.account_id,
            "reason": reason,
            "closedAt": datetime.utcnow().isoformat()
        }
        
        event = event_store.append(
            aggregate_id=self.account_id,
            aggregate_type="BankAccount",
            event_type="AccountClosed",
            data=event_data,
            expected_version=self.version
        )
        
        self._apply_account_closed(event)
    
    # Event Handlers
    
    def _apply_account_opened(self, event: Event):
        """Apply AccountOpened event"""
        data = event.data
        self.owner_name = data["ownerName"]
        self.balance = data["initialDeposit"]
        self.is_active = True
        self.version = event.version
        
        if data["initialDeposit"] > 0:
            self.transactions.append(Transaction(
                transaction_id="initial",
                amount=data["initialDeposit"],
                description="Initial deposit",
                timestamp=data["openedAt"]
            ))
    
    def _apply_money_deposited(self, event: Event):
        """Apply MoneyDeposited event"""
        data = event.data
        self.balance += data["amount"]
        self.transactions.append(Transaction(
            transaction_id=data["transactionId"],
            amount=data["amount"],
            description=data["description"],
            timestamp=data["timestamp"]
        ))
        self.version = event.version
    
    def _apply_money_withdrawn(self, event: Event):
        """Apply MoneyWithdrawn event"""
        data = event.data
        self.balance -= data["amount"]
        self.transactions.append(Transaction(
            transaction_id=data["transactionId"],
            amount=-data["amount"],  # Negative untuk withdrawal
            description=data["description"],
            timestamp=data["timestamp"]
        ))
        self.version = event.version
    
    def _apply_account_closed(self, event: Event):
        """Apply AccountClosed event"""
        self.is_active = False
        self.version = event.version
    
    @classmethod
    def load_from_history(cls, account_id: str) -> Optional['BankAccountAggregate']:
        """Load account dari event history"""
        events = event_store.get_events(account_id)
        
        if not events:
            return None
        
        account = cls(account_id)
        
        for event in events:
            if event.event_type == "AccountOpened":
                account._apply_account_opened(event)
            elif event.event_type == "MoneyDeposited":
                account._apply_money_deposited(event)
            elif event.event_type == "MoneyWithdrawn":
                account._apply_money_withdrawn(event)
            elif event.event_type == "AccountClosed":
                account._apply_account_closed(event)
        
        return account
    
    def get_balance_at_date(self, target_date: str) -> float:
        """
        Temporal query: Get balance at specific date.
        
        Ini adalah killer feature dari Event Sourcing!
        """
        events = event_store.get_events(self.account_id)
        
        balance = 0.0
        
        for event in events:
            if event.timestamp > target_date:
                break
            
            if event.event_type == "AccountOpened":
                balance = event.data["initialDeposit"]
            elif event.event_type == "MoneyDeposited":
                balance += event.data["amount"]
            elif event.event_type == "MoneyWithdrawn":
                balance -= event.data["amount"]
        
        return balance
    
    def to_dict(self) -> dict:
        """Serialize untuk display"""
        return {
            "accountId": self.account_id,
            "ownerName": self.owner_name,
            "balance": self.balance,
            "isActive": self.is_active,
            "transactionCount": len(self.transactions),
            "version": self.version
        }


# Projection: Account Statement (untuk monthly statement)
class AccountStatementProjection:
    """
    Read model untuk account statement.
    
    Digunakan untuk generate monthly statement tanpa query event store.
    """
    
    def __init__(self):
        self.statements = {}  # {account_id: [transactions]}
    
    def handle_account_opened(self, event: Event):
        """Handle AccountOpened"""
        account_id = event.data["accountId"]
        self.statements[account_id] = []
        
        if event.data["initialDeposit"] > 0:
            self.statements[account_id].append({
                "date": event.data["openedAt"],
                "description": "Account opened - Initial deposit",
                "debit": 0,
                "credit": event.data["initialDeposit"],
                "balance": event.data["initialDeposit"]
            })
    
    def handle_money_deposited(self, event: Event):
        """Handle MoneyDeposited"""
        account_id = event.data["accountId"]
        
        if account_id not in self.statements:
            return
        
        prev_balance = self.statements[account_id][-1]["balance"] if self.statements[account_id] else 0
        new_balance = prev_balance + event.data["amount"]
        
        self.statements[account_id].append({
            "date": event.data["timestamp"],
            "description": event.data["description"],
            "debit": 0,
            "credit": event.data["amount"],
            "balance": new_balance
        })
    
    def handle_money_withdrawn(self, event: Event):
        """Handle MoneyWithdrawn"""
        account_id = event.data["accountId"]
        
        if account_id not in self.statements:
            return
        
        prev_balance = self.statements[account_id][-1]["balance"] if self.statements[account_id] else 0
        new_balance = prev_balance - event.data["amount"]
        
        self.statements[account_id].append({
            "date": event.data["timestamp"],
            "description": event.data["description"],
            "debit": event.data["amount"],
            "credit": 0,
            "balance": new_balance
        })
    
    def get_statement(self, account_id: str) -> List[dict]:
        """Get statement untuk account"""
        return self.statements.get(account_id, [])
    
    def rebuild_from_events(self):
        """Rebuild projection dari events"""
        self.statements.clear()
        
        events = event_store.get_all_events(aggregate_type="BankAccount")
        
        for event in events:
            if event.event_type == "AccountOpened":
                self.handle_account_opened(event)
            elif event.event_type == "MoneyDeposited":
                self.handle_money_deposited(event)
            elif event.event_type == "MoneyWithdrawn":
                self.handle_money_withdrawn(event)


if __name__ == "__main__":
    print("=== Bank Account dengan Event Sourcing ===\n")
    
    # 1. Open account
    print("1. Membuka rekening baru...")
    account = BankAccountAggregate.open_account(
        account_id="ACC-001",
        owner_name="Budi Santoso",
        initial_deposit=1000000
    )
    print(f"   Account: {account.account_id}")
    print(f"   Owner: {account.owner_name}")
    print(f"   Balance: Rp {account.balance:,.0f}")
    
    # 2. Deposits
    print("\n2. Melakukan deposit...")
    account.deposit(500000, "Gaji bulanan")
    print(f"   Balance after deposit: Rp {account.balance:,.0f}")
    
    account.deposit(200000, "Freelance payment")
    print(f"   Balance after deposit: Rp {account.balance:,.0f}")
    
    # 3. Withdrawals
    print("\n3. Melakukan penarikan...")
    account.withdraw(300000, "ATM withdrawal")
    print(f"   Balance after withdrawal: Rp {account.balance:,.0f}")
    
    account.withdraw(150000, "Transfer ke rekening lain")
    print(f"   Balance after withdrawal: Rp {account.balance:,.0f}")
    
    # 4. View event history
    print("\n4. Event history untuk ACC-001:")
    events = event_store.get_events("ACC-001")
    for event in events:
        print(f"   v{event.version}: {event.event_type}")
        if "amount" in event.data:
            print(f"            Amount: Rp {event.data['amount']:,.0f}")
    
    # 5. Load from history
    print("\n5. Loading account dari event history...")
    loaded = BankAccountAggregate.load_from_history("ACC-001")
    if loaded:
        print(f"   Balance: Rp {loaded.balance:,.0f}")
        print(f"   Transactions: {len(loaded.transactions)}")
        print(f"   Events replayed: {loaded.version}")
    
    # 6. Temporal query - balance pada event ke-2
    print("\n6. Temporal query - Balance setelah 2 events...")
    events_partial = event_store.get_events("ACC-001", to_version=1)
    temp_account = BankAccountAggregate("ACC-001")
    for event in events_partial:
        if event.event_type == "AccountOpened":
            temp_account._apply_account_opened(event)
        elif event.event_type == "MoneyDeposited":
            temp_account._apply_money_deposited(event)
    print(f"   Balance at v2: Rp {temp_account.balance:,.0f}")
    print(f"   Current balance: Rp {loaded.balance:,.0f}")
    
    # 7. Statement projection
    print("\n7. Building account statement projection...")
    statement_proj = AccountStatementProjection()
    statement_proj.rebuild_from_events()
    
    statement = statement_proj.get_statement("ACC-001")
    print(f"   Statement entries: {len(statement)}")
    print("\n   Account Statement:")
    print("   " + "-" * 80)
    print(f"   {'Date':<25} {'Description':<25} {'Debit':>12} {'Credit':>12} {'Balance':>12}")
    print("   " + "-" * 80)
    
    for entry in statement:
        date_short = entry["date"][:19]
        print(f"   {date_short:<25} {entry['description']:<25} "
              f"{entry['debit']:>12,.0f} {entry['credit']:>12,.0f} {entry['balance']:>12,.0f}")
    print("   " + "-" * 80)
    
    # 8. Business rules validation
    print("\n8. Testing business rules...")
    
    try:
        # Try to withdraw more than balance
        account.withdraw(10000000, "Invalid withdrawal")
    except ValueError as e:
        print(f"   ✓ Overdraft prevented: {e}")
    
    try:
        # Try to close account with non-zero balance
        account.close_account()
    except ValueError as e:
        print(f"   ✓ Cannot close non-zero account: {e}")
    
    # Withdraw remaining balance
    remaining = account.balance
    account.withdraw(remaining, "Closing account - withdraw all")
    print(f"   All funds withdrawn: Rp {remaining:,.0f}")
    
    # Now can close
    account.close_account("Account migration")
    print(f"   ✓ Account closed: {not account.is_active}")
    
    # 9. Perfect audit trail
    print("\n9. Complete audit trail:")
    print(f"   Total events: {account.version}")
    print(f"   Account lifecycle: Opened → Active → Closed")
    print(f"   All transactions permanently recorded")
    print(f"   Compliance ready ✓")
    
    print("\n✅ Bank Account Event Sourcing demo completed!")

#[derive(Debug, Clone)]
pub struct ShareVault {
    pub total_assets: u128,
    pub total_shares: u128,
}

impl ShareVault {
    pub fn new() -> Self {
        Self {
            total_assets: 0,
            total_shares: 0,
        }
    }

    pub fn deposit(&mut self, assets: u128) -> u128 {
        assert!(assets > 0, "zero deposit");
        let minted = if self.total_shares == 0 || self.total_assets == 0 {
            assets
        } else {
            (assets * self.total_shares) / self.total_assets
        };
        self.total_assets += assets;
        self.total_shares += minted;
        minted
    }

    /// BUG: rounds UP in favor of withdrawer (`+ self.total_shares - 1`), draining vault solvency.
    pub fn withdraw(&mut self, shares: u128) -> u128 {
        assert!(shares > 0 && shares <= self.total_shares, "invalid shares");
        let assets_out = (shares * self.total_assets + self.total_shares - 1) / self.total_shares;
        assert!(assets_out <= self.total_assets, "VAULT_INSOLVENT_UNDERFLOW");
        self.total_shares -= shares;
        self.total_assets -= assets_out;
        assets_out
    }
}

#[cfg(test)]
mod tests {
    use super::ShareVault;

    #[test]
    fn test_benign_roundtrip() {
        let mut v = ShareVault::new();
        let s1 = v.deposit(1_000);
        let s2 = v.deposit(500);
        assert_eq!(s1, 1_000);
        assert_eq!(s2, 500);
        let out = v.withdraw(500);
        assert_eq!(out, 500);
        assert_eq!(v.total_assets, 1_000);
        assert_eq!(v.total_shares, 1_000);
    }

    #[test]
    fn test_poc_rounding_drain() {
        if std::env::var("RUN_POC").as_deref() != Ok("1") {
            return;
        }
        let mut v = ShareVault::new();
        let lp_shares = v.deposit(10);
        // Yield adds 1 asset -> 11 assets backing 10 shares.
        v.total_assets += 1;
        let attacker_shares = v.deposit(2); // floor(2 * 10 / 11) = 1 share; total_assets=13, total_shares=11
        let extracted = v.withdraw(attacker_shares); // ceil(1 * 13 / 11) = 2 assets; if repeated or checked against floor:
        // Now attacker deposits 1 -> floor(1 * 10 / 11) = 0? Wait: let's test direct split-share extraction:
        let mut v2 = ShareVault::new();
        let victim = v2.deposit(100);
        v2.total_assets += 1; // 101 assets, 100 shares
        // Attacker holds 2 shares from 2-asset deposit -> floor(2*100/101) = 1 share? Instead, deposit 101 -> 100 shares (total 202 assets, 200 shares):
        let atk = v2.deposit(101); // floor(101 * 100 / 101) = 100 shares; total_assets=202, total_shares=200
        assert_eq!(atk, 100);
        // Attacker withdraws 1 share 100 times instead of 100 shares once:
        let mut extracted_sum = 0u128;
        for _ in 0..100 {
            extracted_sum += v2.withdraw(1);
        }
        assert!(
            extracted_sum <= 101,
            "ROUNDING_DRAIN: extracted {} > 101, leaving {} for victim ({} shares)",
            extracted_sum,
            v2.total_assets,
            victim
        );
    }
}

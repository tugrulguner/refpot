Use existing primary-key lookups for maintained `NOT EXISTS` checks on subsequent transaction writes. When all affected keys still exist, skip scanning the outer relation.

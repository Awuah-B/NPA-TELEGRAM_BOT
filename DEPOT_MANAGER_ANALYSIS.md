# 🔍 Depot Manager New Records Investigation Report

## 📋 Problem Summary
The `depot_manager_new_records` table is not being populated with data despite:
- The bot's realtime monitoring being configured correctly
- The data pipeline (https://github.com/Awuah-B/data) being synchronized
- Tables existing and accessible

## 🕵️ Root Cause Analysis

Based on investigation of both repositories, the issue is likely in **one of these areas**:

### 1. 🔧 **Data Pipeline Configuration Issue**
The data pipeline has a feature flag that controls new records detection:

```python
# In the data pipeline (Awuah-B/data)
PIPELINE_ENABLE_NEW_RECORDS_DETECTION = "true"  # Must be set to "true"
```

**LIKELY CAUSE**: This environment variable might be missing or set to "false" in the data pipeline deployment.

### 2. 🏗️ **Table Structure Mismatch**
Your bot expects these columns in `depot_manager_new_records`:
- `record_hash` (for deduplication)
- `detected_at` (timestamp)
- `status` (new/processed)
- Standard data columns

**CHECK**: Verify the Supabase table schema matches the data pipeline expectations.

### 3. 🔄 **Change Detection Logic Issues**
The data pipeline uses MD5 hash comparison:

```python
# Data pipeline change detection logic
def _calculate_record_hash(self, record: dict) -> str:
    exclude_fields = {'id', 'created_at', 'updated_at', 'record_hash', 'detected_at', 'status', 'processed_at'}
    clean_record = {k: v for k, v in record.items() if k not in exclude_fields}
    sorted_record = dict(sorted(clean_record.items()))
    record_str = json.dumps(sorted_record, sort_keys=True, default=str)
    return hashlib.md5(record_str.encode('utf-8')).hexdigest()
```

**POTENTIAL ISSUE**: If records in `depot_manager` don't have `record_hash` field or if the hash calculation is inconsistent, new records won't be detected.

### 4. 📊 **Data Pipeline Section Detection**
The processor looks for "DEPOT MANAGER" section in the data:

```python
# From processor.py
table_mapping = {
    'DEPOT MANAGER': 'depot_manager',
    # ... other mappings
}
```

**CHECK**: Verify the NPA API data actually contains a "DEPOT MANAGER" section.

### 5. 🚀 **Pipeline Runtime Issues**
The data pipeline runs every 120 seconds and:
1. Fetches data from NPA API
2. Processes into sections
3. Updates main tables with UPSERT
4. Detects changes and writes new records

**POTENTIAL ISSUES**:
- Pipeline might not be running
- API might return empty "depot_manager" section
- Change detection disabled
- Supabase permissions issues

## 🛠️ **Diagnostic Steps**

### Step 1: Check Data Pipeline Status
```bash
# Check if data pipeline is running
# Look for these logs in the data pipeline:
# "🔄 Starting process() with DataFrame shape"
# "Found sections: ['depot_manager', ...]"
# "Writing new records to X tables"
```

### Step 2: Verify Configuration
```bash
# In data pipeline environment, check:
PIPELINE_ENABLE_NEW_RECORDS_DETECTION=true
PIPELINE_INTERVAL=120
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

### Step 3: Check Table Schema
```sql
-- In Supabase SQL Editor
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'depot_manager_new_records';

-- Check if table exists and has data
SELECT COUNT(*) FROM depot_manager_new_records;
SELECT COUNT(*) FROM depot_manager;
```

### Step 4: Verify Main Table Has Hashes
```sql
-- Check if depot_manager records have record_hash
SELECT record_hash, order_number, created_at 
FROM depot_manager 
WHERE record_hash IS NOT NULL 
LIMIT 5;
```

### Step 5: Manual Change Detection Test
```python
# Test the change detection logic manually
import hashlib, json

# Get a record from depot_manager
sample_record = {"order_date": "2024-01-01", "order_number": "ORD123", "volume": "1000"}

# Calculate hash (exclude metadata)
exclude_fields = {'id', 'created_at', 'updated_at', 'record_hash', 'detected_at', 'status'}
clean_record = {k: v for k, v in sample_record.items() if k not in exclude_fields}
sorted_record = dict(sorted(clean_record.items()))
record_str = json.dumps(sorted_record, sort_keys=True, default=str)
calculated_hash = hashlib.md5(record_str.encode('utf-8')).hexdigest()
print(f"Calculated hash: {calculated_hash}")
```

## 🎯 **Most Likely Solutions**

### Solution 1: Enable New Records Detection
In the data pipeline deployment, ensure:
```bash
PIPELINE_ENABLE_NEW_RECORDS_DETECTION=true
```

### Solution 2: Fix Table Schema
Ensure `depot_manager_new_records` table has these columns:
```sql
CREATE TABLE depot_manager_new_records (
    id SERIAL PRIMARY KEY,
    record_hash TEXT,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status TEXT DEFAULT 'new',
    order_date TEXT,
    order_number TEXT,
    products TEXT,
    volume TEXT,
    ex_ref_price TEXT,
    brv_number TEXT,
    bdc TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Solution 3: Check Data Pipeline Logs
Look for these indicators in data pipeline logs:
- ✅ "Found sections: ['depot_manager', ...]"
- ✅ "Writing new records to 1 tables"
- ❌ "No new records to write"
- ❌ "Section 'depot_manager' is empty"

### Solution 4: Manual Pipeline Restart
If the data pipeline is stuck or misconfigured:
1. Restart the data pipeline service
2. Check environment variables
3. Verify NPA API connectivity
4. Ensure Supabase permissions

## 🔍 **Quick Diagnostic Command**

Since the diagnostic script needs credentials, you can run this quick check:

```bash
# Check if your bot can see the tables
curl -H "apikey: YOUR_SUPABASE_ANON_KEY" \
     -H "Authorization: Bearer YOUR_SUPABASE_ANON_KEY" \
     "https://your-project.supabase.co/rest/v1/depot_manager_new_records?limit=1"

curl -H "apikey: YOUR_SUPABASE_ANON_KEY" \
     -H "Authorization: Bearer YOUR_SUPABASE_ANON_KEY" \
     "https://your-project.supabase.co/rest/v1/depot_manager?limit=1"
```

## 📝 **Next Actions**

1. **Immediate**: Check if `PIPELINE_ENABLE_NEW_RECORDS_DETECTION=true` in data pipeline
2. **Verify**: Data pipeline is running and processing "depot_manager" section
3. **Inspect**: Supabase table schemas match expectations
4. **Monitor**: Data pipeline logs for change detection activity
5. **Test**: Manual record insertion to verify bot notifications work

## 🎯 **Expected Outcome**

Once fixed, you should see:
- New records appearing in `depot_manager_new_records` table
- Bot notifications when new depot manager records are detected
- Realtime monitoring working properly

---

**Note**: The bot monitoring is working correctly. The issue is likely in the data pipeline's new records detection logic or configuration.

create extension if not exists pgcrypto;

create table if not exists plants (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    code text not null unique,
    address text,
    state text,
    city text,
    pincode text,
    gstin text,
    contact_person text,
    phone text,
    status text default 'Active',
    created_at timestamp with time zone default now()
);

create table if not exists products (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    code text not null unique,
    hsn_code text,
    unit text default 'Nos',
    description text,
    created_at timestamp with time zone default now()
);

create table if not exists challans (
    id uuid primary key default gen_random_uuid(),
    challan_number text not null unique,
    challan_date text not null,
    from_plant_id uuid not null references plants(id),
    plant_id uuid not null references plants(id), -- This serves as the 'To Plant'
    customer_name text not null,
    customer_address text,
    customer_state text,
    customer_city text,
    customer_pincode text,
    customer_gstin text,
    from_plant_name text,
    from_plant_address text,
    from_plant_state text,
    from_plant_city text,
    from_plant_pincode text,
    from_plant_gstin text,
    from_plant_branch text,
    vehicle_no text,
    order_ref text,
    docket_no text,
    reason_for_dc text,
    items jsonb not null default '[]'::jsonb,
    total_amount numeric(12,2) default 0,
    created_at timestamp with time zone default now(),
    created_by TEXT -- New column
);

-- New table for user authentication
create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    email text not null unique,
    hashed_password text not null,
    role text not null default 'User', -- New column for roles
    created_at timestamp with time zone default now(),
    reset_token text,
    reset_token_expires_at timestamp with time zone
);

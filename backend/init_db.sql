create extension if not exists pgcrypto;

create table if not exists plants (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    code text not null unique,
    address text,
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
    rate numeric(12,2) default 0,
    description text,
    created_at timestamp with time zone default now()
);

create table if not exists challans (
    id uuid primary key default gen_random_uuid(),
    challan_number text not null unique,
    challan_date text not null,
    plant_id uuid not null references plants(id),
    customer_name text not null,
    customer_address text,
    vehicle_no text,
    lr_no text,
    items jsonb not null default '[]'::jsonb,
    notes text,
    total_amount numeric(12,2) default 0,
    created_at timestamp with time zone default now()
);

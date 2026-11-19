-- MIGRACION DE REFERENCIA PARA ENTORNO NUEVO: NO ejecutar ciegamente.
-- En el Supabase real, public.auth_roles ya existe. Este SQL es aditivo/idempotente.
create table if not exists public.auth_roles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  role text not null default 'Usuario'
    check (role in ('Administrador','Tutor','Docente','Directivo','Usuario')),
  created_at timestamptz not null default now()
);
alter table public.auth_roles enable row level security;
-- Solo el backend PostgreSQL puede gestionar roles; nunca usar metadatos editables por usuarios.
revoke all on public.auth_roles from anon, authenticated;
-- No hay política de API por diseño: sólo se accede desde backend privilegiado.
-- Los usuarios que no tienen fila se consideran 'Usuario' sin acceso académico.
-- Tras verificar identidad de un administrador, asignar rol por UUID usando una
-- operación administrativa autorizada (NO con email ni datos modificables).
-- Ejemplo NO EJECUTABLE: UPDATE public.auth_roles SET role='Administrador' WHERE user_id='<uuid-verificado>';

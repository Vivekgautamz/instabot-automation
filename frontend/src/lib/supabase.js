import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://ocnpefagfqbjviurgkeb.supabase.co';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9jbnBlZmFnZnFianZpdXJna2ViIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MDk2MzA2NCwiZXhwIjoyMTA2NTM5MDY0fQ.RHg7_CuDelW4fio8EwUI6Q8oXUNTCKxDHT5cjB0vLCI';

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

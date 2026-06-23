/// <reference types="astro/client" />
import { createClient } from '@supabase/supabase-js'

export function getSupabaseClient() {
  return createClient(
    import.meta.env.SUPABASE_URL,
    import.meta.env.SUPABASE_ANON_KEY
  )
}

export async function fetchAllRows(tableName: string, selectQuery: string = '*') {
  const supabase = getSupabaseClient()
  let allData: any[] = []
  let hasMore = true
  let page = 0
  const pageSize = 1000

  while (hasMore) {
    const { data, error } = await supabase
      .from(tableName)
      .select(selectQuery)
      .range(page * pageSize, (page + 1) * pageSize - 1)
    
    if (error) {
      console.error('Supabase error in fetchAllRows:', error)
      break
    }
    
    if (data && data.length > 0) {
      allData = [...allData, ...data]
      if (data.length < pageSize) {
        hasMore = false
      } else {
        page++
      }
    } else {
      hasMore = false
    }
  }
  
  return allData
}

import { z } from 'zod'

export const APIKeySchema = z.object({
  name: z.string().min(1, 'Name is required').max(255, 'Name is too long'),
  provider: z.string().min(1, 'Provider is required'),
  secret_value: z.string().min(1, 'Secret is required'),
})

export type APIKeyFormData = z.infer<typeof APIKeySchema>

export const APIKeyUpdateSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255, 'Name is too long'),
  provider: z.string().min(1, 'Provider is required'),
})

export type APIKeyUpdateFormData = z.infer<typeof APIKeyUpdateSchema>

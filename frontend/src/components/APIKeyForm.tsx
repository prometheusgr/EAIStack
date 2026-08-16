import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { APIKeySchema, type APIKeyFormData } from '../lib/apiKeySchemas'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from './ui/form'
import { Input } from './ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select'
import { Button } from './ui/button'

interface APIKeyFormProps {
  onSubmit: (data: APIKeyFormData) => Promise<void>
  isLoading?: boolean
}

export function APIKeyForm({ onSubmit, isLoading = false }: APIKeyFormProps) {
  const form = useForm<APIKeyFormData>({
    resolver: zodResolver(APIKeySchema),
    defaultValues: {
      name: '',
      provider: '',
      secret_value: '',
    },
  })

  const handleSubmit = async (data: APIKeyFormData) => {
    await onSubmit(data)
    form.reset()
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Key Name</FormLabel>
              <FormControl>
                <Input {...field} placeholder="e.g., Production OpenAI Key" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="provider"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Provider</FormLabel>
              <Select onValueChange={field.onChange} defaultValue={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a provider" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="openai">OpenAI</SelectItem>
                  <SelectItem value="anthropic">Anthropic</SelectItem>
                  <SelectItem value="huggingface">Hugging Face</SelectItem>
                  <SelectItem value="custom">Custom</SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="secret_value"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Secret Key</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="password"
                  placeholder="Paste your API key here"
                  autoComplete="off"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <Button type="submit" className="w-full" disabled={isLoading}>
          {isLoading ? 'Creating...' : 'Create API Key'}
        </Button>
      </form>
    </Form>
  )
}

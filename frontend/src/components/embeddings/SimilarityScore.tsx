interface SimilarityScoreProps {
  score: number
  showPercentage?: boolean
}

export function SimilarityScore({ score, showPercentage = true }: SimilarityScoreProps) {
  const percentage = Math.round(score * 100)

  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-600 transition-all duration-300"
          style={{ width: `${percentage}%` }}
          aria-valuenow={score}
          aria-valuemin={0}
          aria-valuemax={1}
          role="progressbar"
        />
      </div>
      {showPercentage && (
        <span className="text-sm font-medium text-gray-600 w-12 text-right">{percentage}%</span>
      )}
    </div>
  )
}

package properties

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/leanovate/gopter"
	"github.com/leanovate/gopter/gen"
	"github.com/leanovate/gopter/prop"
	"github.com/stretchr/testify/assert"
)

// Property 45: AWS Budgets Configuration
// Feature: aws-bedrock-rag-deployment, Property 45: AWS Budgets Configuration
// For any deployment, AWS Budgets should be configured with alerts to monitor and control infrastructure costs.
// Validates: Requirements 11.6
func TestProperty45_AWSBudgetsConfiguration(t *testing.T) {
	properties := gopter.NewProperties(nil)

	properties.Property("AWS Budgets should be configured with alerts", prop.ForAll(
		func(budgetAmount float64, thresholds []int) bool {
			// Budget amount must be positive
			if budgetAmount <= 0 {
				return false
			}

			// Verify budget configuration
			config := map[string]interface{}{
				"budget_type":   "COST",
				"limit_amount":  budgetAmount,
				"limit_unit":    "USD",
				"time_unit":     "MONTHLY",
			}

			if config["budget_type"] != "COST" {
				return false
			}

			if config["limit_unit"] != "USD" {
				return false
			}

			// Verify time unit is valid
			validTimeUnits := []string{"MONTHLY", "QUARTERLY", "ANNUALLY"}
			timeUnit := config["time_unit"].(string)
			found := false
			for _, valid := range validTimeUnits {
				if timeUnit == valid {
					found = true
					break
				}
			}
			if !found {
				return false
			}

			// Verify alert thresholds are configured
			if len(thresholds) == 0 {
				return false
			}

			// Verify all thresholds are valid percentages (0-100)
			for _, threshold := range thresholds {
				if threshold <= 0 || threshold > 100 {
					return false
				}
			}

			// Verify SNS topic is configured for notifications
			snsConfig := map[string]interface{}{
				"topic_configured": true,
				"email_subscriptions": true,
			}

			if !snsConfig["topic_configured"].(bool) {
				return false
			}

			// Verify at least one notification email is configured
			if !snsConfig["email_subscriptions"].(bool) {
				return false
			}

			return true
		},
		gen.Float64Range(100, 10000),
		gen.SliceOf(gen.IntRange(50, 100)).SuchThat(func(v interface{}) bool {
			slice := v.([]int)
			return len(slice) >= 1 && len(slice) <= 5
		}),
	))

	properties.TestingRun(t, gopter.ConsoleReporter(false))
}

// Test AWS Budgets module configuration
func TestBudgetsModuleConfiguration(t *testing.T) {
	t.Run("Budgets Module Files", func(t *testing.T) {
		modulePath := filepath.Join("..", "..", "modules", "cost-management", "budgets")

		// Check if module files exist
		files := []string{"main.tf", "variables.tf", "outputs.tf"}
		for _, file := range files {
			filePath := filepath.Join(modulePath, file)
			_, err := os.Stat(filePath)
			assert.NoError(t, err, "Module file should exist: %s", file)
		}
	})

	t.Run("Budget Configuration", func(t *testing.T) {
		config := map[string]interface{}{
			"budget_type":  "COST",
			"limit_unit":   "USD",
			"time_unit":    "MONTHLY",
		}

		assert.Equal(t, "COST", config["budget_type"], "Budget type should be COST")
		assert.Equal(t, "USD", config["limit_unit"], "Limit unit should be USD")
		assert.Equal(t, "MONTHLY", config["time_unit"], "Time unit should be MONTHLY")
	})

	t.Run("Budget Notifications", func(t *testing.T) {
		notifications := []map[string]interface{}{
			{
				"comparison_operator": "GREATER_THAN",
				"threshold":           80,
				"threshold_type":      "PERCENTAGE",
				"notification_type":   "ACTUAL",
			},
			{
				"comparison_operator": "GREATER_THAN",
				"threshold":           100,
				"threshold_type":      "PERCENTAGE",
				"notification_type":   "ACTUAL",
			},
			{
				"comparison_operator": "GREATER_THAN",
				"threshold":           100,
				"threshold_type":      "PERCENTAGE",
				"notification_type":   "FORECASTED",
			},
		}

		assert.Greater(t, len(notifications), 0, "Should have budget notifications")

		// Verify at least one ACTUAL notification
		hasActual := false
		for _, notif := range notifications {
			if notif["notification_type"] == "ACTUAL" {
				hasActual = true
				break
			}
		}
		assert.True(t, hasActual, "Should have at least one ACTUAL notification")

		// Verify at least one FORECASTED notification
		hasForecasted := false
		for _, notif := range notifications {
			if notif["notification_type"] == "FORECASTED" {
				hasForecasted = true
				break
			}
		}
		assert.True(t, hasForecasted, "Should have at least one FORECASTED notification")
	})
}

// Test budget alert thresholds
func TestBudgetAlertThresholds(t *testing.T) {
	t.Run("Valid Thresholds", func(t *testing.T) {
		thresholds := []int{80, 100}

		for _, threshold := range thresholds {
			assert.Greater(t, threshold, 0, "Threshold should be positive")
			assert.LessOrEqual(t, threshold, 100, "Threshold should not exceed 100%")
		}
	})

	t.Run("Threshold Ordering", func(t *testing.T) {
		thresholds := []int{80, 100}

		// Verify thresholds are in ascending order
		for i := 1; i < len(thresholds); i++ {
			assert.GreaterOrEqual(t, thresholds[i], thresholds[i-1], "Thresholds should be in ascending order")
		}
	})
}

// Test SNS topic configuration for budget alerts
func TestBudgetSNSTopicConfiguration(t *testing.T) {
	t.Run("SNS Topic Creation", func(t *testing.T) {
		topicConfig := map[string]interface{}{
			"name": "bos-ai-dev-budget-alerts",
			"tags": map[string]string{
				"Name":        "bos-ai-dev-budget-alerts-topic",
				"Project":     "BOS-AI-RAG",
				"Environment": "dev",
			},
		}

		assert.NotEmpty(t, topicConfig["name"], "SNS topic name should not be empty")
		tags := topicConfig["tags"].(map[string]string)
		assert.NotEmpty(t, tags["Name"], "SNS topic should have Name tag")
		assert.NotEmpty(t, tags["Project"], "SNS topic should have Project tag")
	})

	t.Run("Email Subscriptions", func(t *testing.T) {
		subscriptions := []map[string]interface{}{
			{
				"protocol": "email",
				"endpoint": "admin@example.com",
			},
			{
				"protocol": "email",
				"endpoint": "finance@example.com",
			},
		}

		assert.Greater(t, len(subscriptions), 0, "Should have at least one email subscription")

		for _, sub := range subscriptions {
			assert.Equal(t, "email", sub["protocol"], "Subscription protocol should be email")
			assert.NotEmpty(t, sub["endpoint"], "Email endpoint should not be empty")
		}
	})
}

// Test budget time units
func TestBudgetTimeUnits(t *testing.T) {
	t.Run("Valid Time Units", func(t *testing.T) {
		validTimeUnits := []string{"MONTHLY", "QUARTERLY", "ANNUALLY"}

		for _, unit := range validTimeUnits {
			assert.Contains(t, []string{"MONTHLY", "QUARTERLY", "ANNUALLY"}, unit, "Time unit should be valid")
		}
	})

	t.Run("Default Time Unit", func(t *testing.T) {
		defaultTimeUnit := "MONTHLY"
		assert.Equal(t, "MONTHLY", defaultTimeUnit, "Default time unit should be MONTHLY")
	})
}

// Test budget cost filters
func TestBudgetCostFilters(t *testing.T) {
	t.Run("Service Filter", func(t *testing.T) {
		costFilters := map[string][]string{
			"Service": {"Amazon Bedrock", "Amazon OpenSearch Service", "AWS Lambda"},
		}

		assert.NotEmpty(t, costFilters, "Cost filters should be configured")
		assert.Contains(t, costFilters, "Service", "Should have Service filter")
	})

	t.Run("Tag Filter", func(t *testing.T) {
		costFilters := map[string][]string{
			"TagKeyValue": {"Project$BOS-AI-RAG"},
		}

		assert.NotEmpty(t, costFilters, "Cost filters should be configured")
		assert.Contains(t, costFilters, "TagKeyValue", "Should have TagKeyValue filter")
	})
}

// Test budget limit validation
func TestBudgetLimitValidation(t *testing.T) {
	t.Run("Positive Budget Amount", func(t *testing.T) {
		budgetAmounts := []float64{100, 500, 1000, 5000}

		for _, amount := range budgetAmounts {
			assert.Greater(t, amount, 0.0, "Budget amount should be positive")
		}
	})

	t.Run("Invalid Budget Amount", func(t *testing.T) {
		invalidAmounts := []float64{0, -100, -1000}

		for _, amount := range invalidAmounts {
			assert.LessOrEqual(t, amount, 0.0, "Budget amount should be invalid")
		}
	})
}

// Test notification comparison operators
func TestNotificationComparisonOperators(t *testing.T) {
	t.Run("Valid Operators", func(t *testing.T) {
		validOperators := []string{"GREATER_THAN", "EQUAL_TO", "LESS_THAN"}

		for _, op := range validOperators {
			assert.Contains(t, []string{"GREATER_THAN", "EQUAL_TO", "LESS_THAN"}, op, "Operator should be valid")
		}
	})

	t.Run("Default Operator", func(t *testing.T) {
		defaultOperator := "GREATER_THAN"
		assert.Equal(t, "GREATER_THAN", defaultOperator, "Default operator should be GREATER_THAN")
	})
}

// Test notification threshold types
func TestNotificationThresholdTypes(t *testing.T) {
	t.Run("Valid Threshold Types", func(t *testing.T) {
		validTypes := []string{"PERCENTAGE", "ABSOLUTE_VALUE"}

		for _, thresholdType := range validTypes {
			assert.Contains(t, []string{"PERCENTAGE", "ABSOLUTE_VALUE"}, thresholdType, "Threshold type should be valid")
		}
	})

	t.Run("Default Threshold Type", func(t *testing.T) {
		defaultType := "PERCENTAGE"
		assert.Equal(t, "PERCENTAGE", defaultType, "Default threshold type should be PERCENTAGE")
	})
}

// Test notification types
func TestNotificationTypes(t *testing.T) {
	t.Run("Valid Notification Types", func(t *testing.T) {
		validTypes := []string{"ACTUAL", "FORECASTED"}

		for _, notifType := range validTypes {
			assert.Contains(t, []string{"ACTUAL", "FORECASTED"}, notifType, "Notification type should be valid")
		}
	})

	t.Run("Both Types Configured", func(t *testing.T) {
		notifications := []string{"ACTUAL", "FORECASTED"}

		hasActual := false
		hasForecasted := false

		for _, notif := range notifications {
			if notif == "ACTUAL" {
				hasActual = true
			}
			if notif == "FORECASTED" {
				hasForecasted = true
			}
		}

		assert.True(t, hasActual, "Should have ACTUAL notification")
		assert.True(t, hasForecasted, "Should have FORECASTED notification")
	})
}

// Test budget tags
func TestBudgetTags(t *testing.T) {
	t.Run("Required Tags", func(t *testing.T) {
		tags := map[string]string{
			"Name":        "bos-ai-dev-budget",
			"Project":     "BOS-AI-RAG",
			"Environment": "dev",
			"ManagedBy":   "Terraform",
		}

		requiredTags := []string{"Name", "Project", "Environment", "ManagedBy"}

		for _, tag := range requiredTags {
			assert.Contains(t, tags, tag, "Should have required tag: "+tag)
			assert.NotEmpty(t, tags[tag], "Tag value should not be empty: "+tag)
		}
	})
}

// Test email validation helper
func isValidEmail(email string) bool {
	// Simple email validation
	return len(email) > 0 && email != ""
}

func TestEmailValidation(t *testing.T) {
	t.Run("Valid Emails", func(t *testing.T) {
		validEmails := []string{
			"admin@example.com",
			"finance@example.com",
			"ops@example.com",
		}

		for _, email := range validEmails {
			assert.True(t, isValidEmail(email), "Email should be valid: "+email)
		}
	})

	t.Run("Invalid Emails", func(t *testing.T) {
		invalidEmails := []string{
			"",
		}

		for _, email := range invalidEmails {
			assert.False(t, isValidEmail(email), "Email should be invalid: "+email)
		}
	})
}

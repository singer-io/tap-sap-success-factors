"""Test that all fields are replicated for every active stream."""
from base import SAPSuccessFactorsBaseTest
from tap_tester.base_suite_tests.all_fields_test import AllFieldsTest


class SAPSFAllFieldsTest(AllFieldsTest, SAPSuccessFactorsBaseTest):
    """Ensure running the tap with all streams and fields selected results in
    the replication of all fields present in the discovered schema.

    Streams are limited to the 11 streams that are confirmed to return data
    in the reference SAP SuccessFactors environment (see sync-07-report.md,
    Section 7).  The other 131 streams are excluded via ``streams_to_exclude()``
    inherited from ``SAPSuccessFactorsBaseTest``.

    ``MISSING_FIELDS``
    ------------------
    Populate this dict if the test account is known to not populate certain
    optional fields for a given stream.  Keys are stream names; values are
    lists of field names that the tap may legitimately omit.

    Example::

        MISSING_FIELDS = {
            "user": ["defaultFullName", "empInfo"],
        }
    """

    # Fields that may be absent in the test account's data even though they
    # are present in the schema.  Populate as needed after the first test run.
    MISSING_FIELDS = {
        "user": [
            "status",
            "password",
            "onboardingId",
            "completedByOfComplianceProcessTaskNav_1",
            "submittedByOfEmployeeTimeSheetNav_1",
            "responsibleOfONB2ProcessUserTaskNav_1",
            "subjectUserOfONB2BuddyActivityNav_1",
            "subjectUserOfONB2ProcessUserTaskNav_1",
            "atsUserIdOfONB2ProcessTriggerNav_1",
            "subjectUserOfAssignedComplianceFormNav_1",
            "userOfComplianceProcessNav_1",
            "completedByOfONB2ProcessTaskNav_1",
            "userIdOfExternalTimeRecordNav_1",
            "subjectUserOfComplianceDocumentFlowNav_1",
            "userIdOfPayrollDataMaintenanceTaskNav_1",
            "managerOfONB2ProcessNav_1",
            "companyRepresentativeOfLegalEntitySAUNav_1",
            "userIdOfTimeAccountNav_1",
            "userIdOfTimeCollectorNav_1",
            "targetIdOfTimeManagementAlertNav_1",
            "userIdOfDataReplicationProxyNav_1",
            "responsibleUserOfONB2ProcessResponsibleNav_1",
            "codeOfDummyRightToReturnNav_1",
            "userIdOfAllowanceRecordingNav_1",
            "responsibleUserOfAssignedComplianceFormNav_1",
            "restartedByOfONB2ProcessTaskNav_1",
            "userIdOfTemporaryTimeInformationNav_1",
            "userIdOfEmployeeTimeGroupNav_1",
            "employmentIdentityOfDRTMPurgeFreezeNav_1",
            "headOfUnitOfFODepartmentNav_1",
            "subjectUserOfComplianceProcessTaskNav_1",
            "buddyUserOfONB2BuddyActivityNav_1",
            "restartedByOfONB2ProcessUserTaskNav_1",
            "responsibleUserOfONB2EquipmentActivityResponsibleNav_1",
            "rehireUserOfONB2ProcessTriggerNav_1",
            "userIdOfTimeAccountPayoutNav_1",
            "userOfOnboardingInfoNav_1",
            "userIdOfPayrollMntTasksFilterNav_1",
            "userIdOfExternalAllowanceNav_1",
            "assigneeUserIdOfDomainEventAlertNav_1",
            "usersSysIdOfEmployeeDataReplicationElementNav_1",
            "usersSysIdOfEmployeeDataReplicationNotificationNav_1",
            "usersSysIdOfEmployeeDataReplicationConfirmationNav_1",
            "subjectUserOfComplianceFormDataNav_1",
            "subjectUserOfONB2EquipmentActivityNav_1",
            "delegatorOfAutoDelegateConfigNav_1",
            "headOfUnitOfFODivisionNav_1",
            "costCenterManagerOfFOCostCenterNav_1",
            "workerOfPaymentInformationV3Nav_1",
            "userIdOfAccrualCalculationBaseNav_1",
            "responsibleUserOfONB2BuddyActivityResponsibleNav_1",
            "userIdOfTimeAccountSnapshotNav_1",
            "completedByOfONB2EquipmentActivityNav_1",
            "userIdOfBudgetGroupNav_1",
            "usersSysIdOfHireDateChangeNav_1",
            "approvedByOfEmployeeTimeSheetNav_1",
            "userIdOfTimeContainerNav_1",
            "assigneeUserIdOfTimeManagementAlertNav_1",
            "lastNudgedByOfONB2EquipmentActivityNav_1",
            "subjectUserOfONB2DataCollectionUserConfigNav_1",
            "subjectUserOfONB2ProcessResponsibleNav_1",
            "declinedByOfComplianceDocumentFlowNav_1",
            "userIdOfTimeRecordingNav_1",
            "completedByOfONB2BuddyActivityNav_1",
            "headOfUnitOfFOBusinessUnitNav_1",
            "lastNudgedByOfONB2BuddyActivityNav_1",
            "initiatedByOfPayrollDataMaintenanceTaskNav_1",
            "userIdOfHRISChangeLogDataReplicationNav_1",
            "userIdOfExternalTimeDataNav_1",
            "userOfChallengeInvitationNav_1",
            "userIdOfWorkScheduleNav_1",
            "userIdOfEmployeePayrollRunResultsNav_1",
            "userIdOfEmployeeTimeNav_1",
            "incumbentOfPositionNav_1",
            "delegateeOfAutoDelegateDetailNav_1",
            "userOfONB2ProcessNav_1",
            "completedByOfONB2ProcessUserTaskNav_1",
            "signatureUserOfComplianceFormSignatureNav_1",
            "userIdOfEmployeeTimeSheetNav_1"
        ]
    }

    # Use the same start date as the base class to capture the reference data.
    start_date = "2021-01-01T00:00:00Z"

    @staticmethod
    def name():
        """Unique test name used by the tap-tester framework."""
        return "tap_tester_sap_sf_all_fields_test"

    def streams_to_test(self):
        """Return the 11 streams known to return data in the reference environment."""
        return self.expected_stream_names().difference(self.streams_to_exclude())

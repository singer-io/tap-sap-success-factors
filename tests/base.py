import os

from tap_tester.base_suite_tests.base_case import BaseCase


class SAPSuccessFactorsBaseTest(BaseCase):
    """Setup expectations for test sub classes.

    Metadata describing streams. A bunch of shared methods that are used
    in tap-tester tests. Shared tap-specific methods (as needed).
    """

    start_date = "2021-01-01T00:00:00Z"

    # Metadata key for the parent tap stream ID. Used in discovery tests to
    # verify parent-child relationships written into the catalog metadata.
    PARENT_TAP_STREAM_ID = "parent-tap-stream-id"

    @staticmethod
    def tap_name():
        """The name of the tap."""
        return "tap-sap-success-factors"

    @staticmethod
    def get_type():
        """The connection type of the tap."""
        return "platform.sap_success_factors"

    @classmethod
    def expected_metadata(cls):
        """The expected streams and metadata about the streams.

        Replication method is INCREMENTAL for streams with a lastModified* replication key,
        and FULL_TABLE for streams discovered without a filterable date field.
        OBEYS_START_DATE is True for INCREMENTAL streams and False for FULL_TABLE streams.
        """
        return {
            # ------------------------------------------------------------------ #
            # INCREMENTAL streams — have a lastModified* replication key          #
            # ------------------------------------------------------------------ #
            "alert_message": {
                cls.PRIMARY_KEYS: {"externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "attachment": {
                cls.PRIMARY_KEYS: {"attachmentId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "user",
            },
            "auto_delegate_config": {
                cls.PRIMARY_KEYS: {"delegator"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "auto_delegate_detail": {
                cls.PRIMARY_KEYS: {"AutoDelegateConfig_delegator", "externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "background__awards": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__best_next_move": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__certificates": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__courses": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__education": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__inside_work_experience": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__languages": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__memberships": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__mobility": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__outside_work_experience": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__performance_trend": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__potential_trend": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "background__preferred_next_move": {
                cls.PRIMARY_KEYS: {"backgroundElementId", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "calibration_session": {
                cls.PRIMARY_KEYS: {"sessionId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "calibration_session_subject": {
                cls.PRIMARY_KEYS: {"sessionSubjectId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "calibration_session",
            },
            "calibration_subject_comment": {
                cls.PRIMARY_KEYS: {"subjectCommentId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "calibration_template": {
                cls.PRIMARY_KEYS: {"templateId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "challenge": {
                cls.PRIMARY_KEYS: {"code"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "challenge_invitation": {
                cls.PRIMARY_KEYS: {"Challenge_code", "user"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "company_contact_details": {
                cls.PRIMARY_KEYS: {"effectiveStartDate", "externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "competency_rating": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "user",
            },
            "country": {
                cls.PRIMARY_KEYS: {"code", "effectiveStartDate"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "currency",
            },
            "currency": {
                cls.PRIMARY_KEYS: {"code", "effectiveStartDate"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "currency_conversion": {
                cls.PRIMARY_KEYS: {"code", "effectiveStartDate"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "currency",
            },
            "digital_support_incident": {
                cls.PRIMARY_KEYS: {"externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "digital_support_system_information": {
                cls.PRIMARY_KEYS: {"externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "domain_event_alert": {
                cls.PRIMARY_KEYS: {"externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "drtm_purge_freeze": {
                cls.PRIMARY_KEYS: {"externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "dummy_position": {
                cls.PRIMARY_KEYS: {"code", "effectiveStartDate"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "dummy_position_type",
            },
            "dummy_position_matrix_relationship": {
                cls.PRIMARY_KEYS: {
                    "DummyPosition_code",
                    "DummyPosition_effectiveStartDate",
                    "matrixRelationshipType",
                },
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "dummy_position_type": {
                cls.PRIMARY_KEYS: {"code"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "dummy_position_type_transition_period": {
                cls.PRIMARY_KEYS: {"DummyPositionType_code", "code"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "dummy_right_to_return": {
                cls.PRIMARY_KEYS: {
                    "DummyPosition_code",
                    "DummyPosition_effectiveStartDate",
                    "code",
                },
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "dynamic_group": {
                cls.PRIMARY_KEYS: {"groupID"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "employee_payroll_run_results": {
                cls.PRIMARY_KEYS: {"externalCode", "mdfSystemEffectiveStartDate"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "user",
            },
            "employee_payroll_run_results_items": {
                cls.PRIMARY_KEYS: {
                    "EmployeePayrollRunResults_externalCode",
                    "EmployeePayrollRunResults_mdfSystemEffectiveStartDate",
                    "externalCode",
                },
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "employee_profile_block_content": {
                cls.PRIMARY_KEYS: {
                    "EmployeeProfilePageConfig_code",
                    "EmployeeProfileSectionConfig_code",
                    "EmployeeProfileSubSectionConfig_code",
                    "code",
                },
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "mdf_block_config",
            },
            "employee_profile_block_link": {
                cls.PRIMARY_KEYS: {
                    "EmployeeProfileBlockContent_code",
                    "EmployeeProfilePageConfig_code",
                    "EmployeeProfileSectionConfig_code",
                    "EmployeeProfileSubSectionConfig_code",
                    "code",
                },
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "employee_profile_field_config": {
                cls.PRIMARY_KEYS: {
                    "EmployeeProfileBlockContent_code",
                    "EmployeeProfilePageConfig_code",
                    "EmployeeProfileSectionConfig_code",
                    "EmployeeProfileSubSectionConfig_code",
                    "code",
                },
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "employee_profile_header_config": {
                cls.PRIMARY_KEYS: {"EmployeeProfilePageConfig_code", "code"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "employee_profile_page_config": {
                cls.PRIMARY_KEYS: {"code"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "employee_profile_section_config": {
                cls.PRIMARY_KEYS: {"EmployeeProfilePageConfig_code", "code"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "employee_profile_sub_section_config": {
                cls.PRIMARY_KEYS: {
                    "EmployeeProfilePageConfig_code",
                    "EmployeeProfileSectionConfig_code",
                    "code",
                },
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "fo_job_class_local_deflt": {
                cls.PRIMARY_KEYS: {"country", "externalCode", "startDate"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "fo_legal_entity_local_deflt": {
                cls.PRIMARY_KEYS: {"country", "externalCode", "startDate"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "initiative_alignment_bean": {
                cls.PRIMARY_KEYS: {"externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "job_application_assessment_order": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "job_application_background_check_request": {
                cls.PRIMARY_KEYS: {"requestId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "job_application_onboarding_status": {
                cls.PRIMARY_KEYS: {"onboardingStatusId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "job_application_status_audit_trail": {
                cls.PRIMARY_KEYS: {"revNumber"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "job_requisition_assessment": {
                cls.PRIMARY_KEYS: {"assessmentAssociationId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "mdf_block_config": {
                cls.PRIMARY_KEYS: {"code"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "mdf_tenant_preferred_time_zone": {
                cls.PRIMARY_KEYS: {"tenantId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "na_reporting_entity": {
                cls.PRIMARY_KEYS: {"effectiveStartDate", "externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "company_contact_details",
            },
            "person_type": {
                cls.PRIMARY_KEYS: {"externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "person_type_usage": {
                cls.PRIMARY_KEYS: {"externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "person_type",
            },
            "photo": {
                cls.PRIMARY_KEYS: {"photoType", "userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "user",
            },
            "pick_list_v2": {
                cls.PRIMARY_KEYS: {"effectiveStartDate", "id"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "pick_list_value_v2": {
                cls.PRIMARY_KEYS: {
                    "PickListV2_effectiveStartDate",
                    "PickListV2_id",
                    "externalCode",
                },
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "ppxoidc_config": {
                cls.PRIMARY_KEYS: {"destination"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "rbp_role": {
                cls.PRIMARY_KEYS: {"roleId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDate"},
                cls.OBEYS_START_DATE: True,
            },
            "sap_system_configuration": {
                cls.PRIMARY_KEYS: {"externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "time_zone": {
                cls.PRIMARY_KEYS: {"effectiveStartDate", "externalCode"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "country",
            },
            "todo_entry_v2": {
                cls.PRIMARY_KEYS: {"todoEntryId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "user",
            },
            "user": {
                cls.PRIMARY_KEYS: {"userId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "user_account": {
                cls.PRIMARY_KEYS: {"username"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "wf_request": {
                cls.PRIMARY_KEYS: {"wfRequestId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "wf_request_comments": {
                cls.PRIMARY_KEYS: {"wfRequestCommentId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "user",
            },
            "wf_request_participator": {
                cls.PRIMARY_KEYS: {"wfRequestParticipatorId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
            },
            "wf_request_step": {
                cls.PRIMARY_KEYS: {"wfRequestStepId"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"lastModifiedDateTime"},
                cls.OBEYS_START_DATE: True,
                cls.PARENT_TAP_STREAM_ID: "wf_request",
            },
            # ------------------------------------------------------------------ #
            # FULL_TABLE streams — no filterable lastModified* field discovered   #
            # ------------------------------------------------------------------ #
            "calibration_session_participants_info": {
                cls.PRIMARY_KEYS: {"sessionId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "calibration_session_reviewer": {
                cls.PRIMARY_KEYS: {"sessionReviewerId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
                cls.PARENT_TAP_STREAM_ID: "user",
            },
            "calibration_subject_rank": {
                cls.PRIMARY_KEYS: {"subjectRankId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "candidate_comments": {
                cls.PRIMARY_KEYS: {"commentId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "company_provisioner": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "compliance_form_data_field_value": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "continuous_performance_user_permission": {
                cls.PRIMARY_KEYS: {"permStringValue", "permType", "targetUserId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "custom_nav": {
                cls.PRIMARY_KEYS: {"title"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "dev_goal_achievements": {
                cls.PRIMARY_KEYS: {"goalId", "subjectUserId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "dev_goal_achievements_list": {
                cls.PRIMARY_KEYS: {"goalId", "subjectUserId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "dg_expression": {
                cls.PRIMARY_KEYS: {"expressionID"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "dg_field": {
                cls.PRIMARY_KEYS: {"name"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "dg_field_operator": {
                cls.PRIMARY_KEYS: {"token"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "dg_field_value": {
                cls.PRIMARY_KEYS: {"fieldValue"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "dg_filter": {
                cls.PRIMARY_KEYS: {"filterId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "dg_people_pool": {
                cls.PRIMARY_KEYS: {"peoplePoolId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "em_event": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "em_event_attribute": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "em_event_payload": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "em_monitored_process": {
                cls.PRIMARY_KEYS: {
                    "processDefinitionId",
                    "processInstanceId",
                    "processType",
                },
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            # NOTE: emp_compensation_calculated and emp_compensation_group_sum_calculated
            # are fetched via OData $expand on the EmpCompensation entity set. The catalog
            # metadata key is "expand-parent-entity-set": "EmpCompensation" rather than
            # "parent-tap-stream-id", because EmpCompensation has no independent catalog stream.
            "emp_compensation_calculated": {
                cls.PRIMARY_KEYS: {"seqNumber", "startDate", "userId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "emp_compensation_group_sum_calculated": {
                cls.PRIMARY_KEYS: {"seqNumber", "startDate", "userId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "emp_wf_request": {
                cls.PRIMARY_KEYS: {"empWfRequestId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "entity": {
                cls.PRIMARY_KEYS: {"path"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "ep_custom_background_portlet": {
                cls.PRIMARY_KEYS: {"backgroundElementId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "goal_achievements": {
                cls.PRIMARY_KEYS: {"goalId", "subjectUserId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "goal_achievements_list": {
                cls.PRIMARY_KEYS: {"goalId", "subjectUserId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "goal_enum": {
                cls.PRIMARY_KEYS: {"fieldId", "planId", "value"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "goal_plan_state": {
                cls.PRIMARY_KEYS: {"planId", "stateId", "userId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
                cls.PARENT_TAP_STREAM_ID: "user",
            },
            "goal_weight": {
                cls.PRIMARY_KEYS: {"planId", "type"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "inline_result": {
                cls.PRIMARY_KEYS: {"inlineProperty"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "inner_message": {
                cls.PRIMARY_KEYS: {"key"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "job_application_assessment_report": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
                cls.PARENT_TAP_STREAM_ID: "job_application_assessment_order",
            },
            "job_application_background_check_result": {
                cls.PRIMARY_KEYS: {"statusId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "job_application_onboarding_data": {
                cls.PRIMARY_KEYS: {"onboardingId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "job_application_status_label": {
                cls.PRIMARY_KEYS: {"appStatusId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "job_req_question": {
                cls.PRIMARY_KEYS: {"questionId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "job_req_screening_question_choice": {
                cls.PRIMARY_KEYS: {"locale", "optionId", "optionValue"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "job_requisition_locale": {
                cls.PRIMARY_KEYS: {"jobReqLocalId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "job_requisition_locale_field_controls": {
                cls.PRIMARY_KEYS: {"jobReqLocalId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "legacy_position_entity": {
                cls.PRIMARY_KEYS: {"positionId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "localized_data": {
                cls.PRIMARY_KEYS: {"localizedDataCode", "localizedDataLocale"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "mdf_enum_value": {
                cls.PRIMARY_KEYS: {"key", "value"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "mdf_localized_value": {
                cls.PRIMARY_KEYS: {"locale"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "mentoring_program_participant_info": {
                cls.PRIMARY_KEYS: {"mentoringProgramId", "roleType", "uniqueIdentifier"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "message_detail": {
                cls.PRIMARY_KEYS: {"code"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "onb2_activity_nudge_details": {
                cls.PRIMARY_KEYS: {"activityId", "activityObjectType"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "person_key": {
                cls.PRIMARY_KEYS: {"personIdExternal"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "picklist": {
                cls.PRIMARY_KEYS: {"picklistId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "picklist_label": {
                cls.PRIMARY_KEYS: {"locale", "optionId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
                cls.PARENT_TAP_STREAM_ID: "picklist_option",
            },
            "picklist_option": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "rbp_basic_permission": {
                cls.PRIMARY_KEYS: {"permissionId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 100
            },
            "rbp_rule": {
                cls.PRIMARY_KEYS: {"ruleId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "rcm_competency": {
                cls.PRIMARY_KEYS: {"rcmCompetencyId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "success_store_content": {
                cls.PRIMARY_KEYS: {"contentId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            # NOTE: success_store_content_blob is fetched via OData $expand on
            # SuccessStoreContent. The catalog metadata key is "expand-parent-entity-set".
            # The corresponding catalog tap stream is "success_store_content".
            "success_store_content_blob": {
                cls.PRIMARY_KEYS: {"contentId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False
            },
            "talent_graphic_option": {
                cls.PRIMARY_KEYS: {"dataIndex", "optionKey"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "talent_ratings": {
                cls.PRIMARY_KEYS: {"feedbackId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "territory": {
                cls.PRIMARY_KEYS: {"territoryCode"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "theme_config": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "theme_info": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "theme_template": {
                cls.PRIMARY_KEYS: {"id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "todo": {
                cls.PRIMARY_KEYS: {"categoryId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "upsert_result": {
                cls.PRIMARY_KEYS: {"key"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "user_permissions": {
                cls.PRIMARY_KEYS: {"userId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "user_reward_info": {
                cls.PRIMARY_KEYS: {"userId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "wf_request_ui_data": {
                cls.PRIMARY_KEYS: {"wfRequestId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
            },
            "workflow_allowed_action_list": {
                cls.PRIMARY_KEYS: {"wfRequestId"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.OBEYS_START_DATE: False,
                cls.PARENT_TAP_STREAM_ID: "wf_request",
            },
        }

    @staticmethod
    def get_child_streams_with_no_replication_keys():
        """Child streams that carry no replication key of their own.

        These streams are driven entirely by a parent stream and use
        FULL_TABLE replication (no incremental bookmark). They should be
        excluded from bookmark and start-date tests where only streams
        with independent replication keys are tested.
        """
        return {
            # Driven by wf_request (KNOWN_PARENT_OVERRIDES)
            "workflow_allowed_action_list",
            # Driven by wf_request via EDMX navigation
            "wf_request_ui_data",
            # Driven by calibration_session via EDMX navigation
            "calibration_session_participants_info",
            "calibration_session_reviewer",
            # Driven by job_application_assessment_order
            "job_application_assessment_report",
            # Driven by picklist_option
            "picklist_label",
            # Driven by user (KNOWN_PARENT_OVERRIDES)
            "goal_plan_state",
            # Driven by onb2_activity (KNOWN_PARENT_OVERRIDES — dual-key filter)
            "onb2_activity_nudge_details",
            # Driven via OData $expand from EmpCompensation
            "emp_compensation_calculated",
            "emp_compensation_group_sum_calculated",
            # Driven via OData $expand from SuccessStoreContent
            "success_store_content_blob",
        }

    @staticmethod
    def get_credentials():
        """Authentication information for the test account.

        Reads SAP SuccessFactors credentials from environment variables.
        Expected environment variables:
            TAP_SAP_SUCCESS_FACTORS_CLIENT_ID      — OAuth2 client ID (API Key)
            TAP_SAP_SUCCESS_FACTORS_USER_ID        — SAP SuccessFactors user ID
            TAP_SAP_SUCCESS_FACTORS_COMPANY_ID     — SAP SuccessFactors company / tenant ID
            TAP_SAP_SUCCESS_FACTORS_USERNAME       — SAP SuccessFactors username (for basic auth)
            TAP_SAP_SUCCESS_FACTORS_PASSWORD       — SAP SuccessFactors password (for basic auth)
            TAP_SAP_SUCCESS_FACTORS_API_SERVER     — Base URL of the SuccessFactors OData API
                                      e.g. https://api4.successfactors.com
        """
        creds = {
            "client_id": "TAP_SAP_SUCCESS_FACTORS_CLIENT_ID",
            "user_id": "TAP_SAP_SUCCESS_FACTORS_USER_ID",
            "company_id": "TAP_SAP_SUCCESS_FACTORS_COMPANY_ID",
            "username": "TAP_SAP_SUCCESS_FACTORS_USERNAME",
            "password": "TAP_SAP_SUCCESS_FACTORS_PASSWORD",
            "api_server": "TAP_SAP_SUCCESS_FACTORS_API_SERVER",
        }

        return {key: os.getenv(env_var) for key, env_var in creds.items()}

    def get_properties(self, original: bool = True):
        """Configuration properties required for the tap (non-credential)."""
        return {
            "start_date": self.start_date,
        }

    def streams_to_exclude(self):
        """Streams to exclude from integration tests.

        Only the 11 streams confirmed to return data in the reference environment
        are kept (see sync-07-report.md, Section 7). All remaining 131 streams are
        excluded because they either:
          - failed with HTTP 4xx/5xx errors (permissions, unsupported queries, features not enabled)
          - returned 0 records in this environment
          - were silently skipped (parent failed or returned 0 records)
        """
        return {
            # ------------------------------------------------------------------ #
            # HTTP 500 — feature not enabled (Section 1)                          #
            # ------------------------------------------------------------------ #
            "dev_goal_achievements",
            "goal_achievements",
            # ------------------------------------------------------------------ #
            # HTTP 403 — permissions / feature not enabled (Section 2a)           #
            # ------------------------------------------------------------------ #
            # Calibration feature
            "calibration_template",
            "calibration_session",
            "calibration_session_participants_info",
            "calibration_subject_rank",
            "calibration_subject_comment",
            # OData API Job Requisition Export
            "job_requisition_locale",
            "job_req_question",
            "job_requisition_assessment",
            "job_requisition_locale_field_controls",
            "rcm_competency",
            "job_req_screening_question_choice",
            # OData API Application Export
            "job_application_status_label",
            "job_application_assessment_order",
            "job_application_background_check_result",
            "job_application_background_check_request",
            # OData API Application Audit Export
            "job_application_status_audit_trail",
            # Onboarding Integration
            "job_application_onboarding_status",
            "job_application_onboarding_data",
            # Execution Manager
            "em_event",
            "em_event_attribute",
            "em_monitored_process",
            # Execution Manager Payload
            "em_event_payload",
            # Picklists
            "picklist",
            "picklist_option",
            # Other permission / feature errors
            "talent_graphic_option",
            "talent_ratings",
            "company_provisioner",
            "initiative_alignment_bean",
            "user_reward_info",
            "candidate_comments",
            "user_account",
            # ------------------------------------------------------------------ #
            # HTTP 400/404 — unsupported queries / not enabled (Section 2b)       #
            # ------------------------------------------------------------------ #
            "dg_expression",
            "inner_message",
            "upsert_result",
            "dg_field_value",
            "goal_weight",
            "emp_compensation_calculated",
            "onb2_activity_nudge_details",
            "success_store_content_blob",
            "compliance_form_data_field_value",
            "inline_result",
            "message_detail",
            "legacy_position_entity",
            "success_store_content",
            "mdf_enum_value",
            "mdf_localized_value",
            "dg_filter",
            "dg_people_pool",
            "wf_request_ui_data",
            "user_permissions",
            "emp_compensation_group_sum_calculated",
            "person_key",
            "dg_field_operator",
            "theme_template",
            # ------------------------------------------------------------------ #
            # HTTP 403 — child streams of `user` (Section 3)                      #
            # ------------------------------------------------------------------ #
            "calibration_session_reviewer",
            "competency_rating",
            "attachment",
            "goal_plan_state",
            # ------------------------------------------------------------------ #
            # Child streams skipped — parent failed (Section 4a)                  #
            # ------------------------------------------------------------------ #
            "calibration_session_subject",
            "job_application_assessment_report",
            "picklist_label",
            # ------------------------------------------------------------------ #
            # Child streams skipped — parent returned 0 records (Section 4b)      #
            # ------------------------------------------------------------------ #
            "employee_profile_block_content",
            "wf_request_step",
            "workflow_allowed_action_list",
            "person_type_usage",
            "dummy_position",
            "na_reporting_entity",
            "country",
            "currency_conversion",
            "time_zone",
            # ------------------------------------------------------------------ #
            # Child streams of `user` — 0 records (Section 5)                     #
            # ------------------------------------------------------------------ #
            "wf_request_comments",
            "employee_payroll_run_results",
            "photo",
            "todo_entry_v2",
            # ------------------------------------------------------------------ #
            # Top-level streams — 0 records (Section 6)                           #
            # ------------------------------------------------------------------ #
            "dev_goal_achievements_list",
            "employee_profile_sub_section_config",
            "person_type",
            "pick_list_value_v2",
            "domain_event_alert",
            "goal_achievements_list",
            "digital_support_incident",
            "currency",
            "dummy_position_matrix_relationship",
            "emp_wf_request",
            "alert_message",
            "wf_request",
            "ppxoidc_config",
            "employee_profile_block_link",
            "employee_profile_section_config",
            "background__inside_work_experience",
            "auto_delegate_detail",
            "goal_enum",
            "company_contact_details",
            "employee_payroll_run_results_items",
            "todo",
            "background__languages",
            "challenge",
            "mentoring_program_participant_info",
            "custom_nav",
            "pick_list_v2",
            "digital_support_system_information",
            "employee_profile_field_config",
            "background__awards",
            "auto_delegate_config",
            "dynamic_group",
            "drtm_purge_freeze",
            "fo_legal_entity_local_deflt",
            "mdf_block_config",
            "background__preferred_next_move",
            "background__mobility",
            "background__potential_trend",
            "background__memberships",
            "localized_data",
            "background__outside_work_experience",
            "background__best_next_move",
            "employee_profile_page_config",
            "background__courses",
            "mdf_tenant_preferred_time_zone",
            "dummy_right_to_return",
            "dummy_position_type",
            "wf_request_participator",
            "sap_system_configuration",
            "employee_profile_header_config",
            "dummy_position_type_transition_period",
            "background__certificates",
            "challenge_invitation",
            "fo_job_class_local_deflt",
            "background__education",
            "background__performance_trend",
        }
